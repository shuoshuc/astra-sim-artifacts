#!/bin/bash

# ============================================================================
# sweep_astrasim.sh
# 
# This script sweeps ASTRA-sim simulations across various workload
# configurations. The work flow for each config is as follows:
#   1. Select the appropriate sys.json based on the parallelism dimensions.
#   2. Generate the trace using STG.
#   3. Create the network.yaml file. Only supports TPUv4 and HGX H100 for now.
#   4. Run ASTRA-sim with the generated STG trace, generated network.yaml, and 
#      provided sys.json and remote_mem.json.
#   5. Save ASTRA-sim statistics to output directory.
# ============================================================================

# Help/Usage
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  cat << EOF
Usage: $0 topology sys1d sys2d sys3d remote_mem.json [output_dir] [dp_values] [tp_values] [pp_values] [batch_size] [micro_batch_values] [models]

Required arguments:
  topology           Topology type ("tpu" or "hgx"). "tpu" uses TPUv4 network config, "hgx" uses HGX H100 network config
  sys1d              Path to 1D system config that corresponds to the selected topology.
  sys2d              Path to 2D system config that corresponds to the selected topology.
  sys3d              Path to 3D system config that corresponds to the selected topology.
  remote_mem.json    Path to remote memory config

Optional arguments:
  output_dir         Output directory (default: /app/examples/sweep_astrasim/)
  dp_values          Comma-separated DP values (default: "1,2,4")
  tp_values          Comma-separated TP values (default: "1,2,4")
  pp_values          Comma-separated PP values (default: "1,2,4")
  batch_size         Batch size for STG (default: 64)
  micro_batch_values Comma-separated micro-batch sizes (default: "-1,16,32")
  models             Comma-separated model list (default: "dense,gpt")

Examples:
  ./sweep_astrasim.sh tpu sys1d.json sys2d.json sys3d.json remote_mem.json
  ./sweep_astrasim.sh tpu sys1d.json sys2d.json sys3d.json remote_mem.json /app/examples/sweep_astrasim/ "1,2,4" "1,2,4" "1,2,4" 64 "-1,16,32" "dense,gpt"
EOF
  exit 0
fi

# Check for required args
if [ $# -lt 5 ]; then
  echo "[sweep_astrasim] Usage: $0 topology sys1d sys2d sys3d remote_mem.json [output_dir] [dp_values] [tp_values] [pp_values] [batch_size] [micro_batch_values] [models]"
  exit 1
fi

# Required args
topology=$1
sys_cfg_1d=$2
sys_cfg_2d=$3
sys_cfg_3d=$4
remote_mem_cfg=$5

# Default args
OUTPUT_DIR=${6:-"/app/examples/sweep_astrasim/"}
dp_arg=${7:-"1,2,4"}
tp_arg=${8:-"1,2,4"}
pp_arg=${9:-"1,2,4"}
batch_size=${10:-64}
micro_arg=${11:-"-1"}
model_arg=${12:-"dense,gpt"}
ep=1  # fixed for now

# Directories and binaries
ASTRASIM_DIR="/app/astra-sim"
STG_DIR="$ASTRASIM_DIR/symbolic_tensor_graph"
TEMP_DIR="$OUTPUT_DIR/temp"

mkdir -p "$OUTPUT_DIR"
mkdir -p "$TEMP_DIR"

ASTRASIM_BIN="$ASTRASIM_DIR/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware"

# Parse list args
IFS=',' read -r -a dp_values <<< "$dp_arg"
IFS=',' read -r -a tp_values <<< "$tp_arg"
IFS=',' read -r -a pp_values <<< "$pp_arg"
IFS=',' read -r -a micro_batch_values <<< "$micro_arg"
IFS=',' read -r -a models <<< "$model_arg"

# Loop through all combinations of DP/TP/PP/micro-batch/model
for model in "${models[@]}"; do
  for dp in "${dp_values[@]}"; do
    for tp in "${tp_values[@]}"; do
      for pp in "${pp_values[@]}"; do
        for micro_batch in "${micro_batch_values[@]}"; do
          echo "[sweep] [$(date '+%m-%d %H:%M:%S')] Sweeping $topology $model dp=$dp tp=$tp pp=$pp mb=$micro_batch"

          npus_count=$((dp * tp * pp * ep))

          # Check npus_count
          if [ "$npus_count" -eq 1 ]; then
            echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    Skipping $topology $model dp=$dp tp=$tp pp=$pp mb=$micro_batch"
            echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    Reason: ASTRA-sim requires more than 1 NPU"
            continue
          fi

          if [ "$npus_count" -gt 16384 ]; then
            echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    Skipping $topology $model dp=$dp tp=$tp pp=$pp mb=$micro_batch"
            echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    Reason: Skipping configs with >16384 NPUs for STG computation time feasibility"
            continue
          fi

          # Check parallelism dimension and select sys config
          dims=0
          [[ $dp -gt 1 ]] && ((dims++))
          [[ $tp -gt 1 ]] && ((dims++))
          [[ $pp -gt 1 ]] && ((dims++))

          case $dims in
              1) sys_cfg="$sys_cfg_1d" ;;
              2) sys_cfg="$sys_cfg_2d" ;;
              3) sys_cfg="$sys_cfg_3d" ;;
              *)
                  echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    Skipping $topology $model dp=$dp tp=$tp pp=$pp ep=$ep mb=$micro_batch"
                  echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    Reason: unsupported parallelism dim ($dims) - must be 1D, 2D, or 3D"
                  continue
                  ;;
          esac

          # Run symbolic tensor graph
          trace_name="${topology}_${model}_${dp}_${tp}_${pp}_ep${ep}_mb${micro_batch}"
          trace_path="$TEMP_DIR/traces/$trace_name"
          mkdir -p "$trace_path"

          echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    Running STG for $topology $model dp=$dp tp=$tp pp=$pp mb=$micro_batch"
          stg_start=$SECONDS
          (
            cd "$STG_DIR" || exit
            python main.py \
              --output_dir "$trace_path" \
              --output_name "$trace_name" \
              --model_type "$model" \
              --dp $dp --tp $tp --sp 1 --ep $ep --pp $pp \
              --micro_batch $micro_batch \
              --batch $batch_size \
              --weight_sharded 0 \
              --chakra_schema_version v0.0.4
          )
          stg_elapsed=$(( SECONDS - stg_start ))
          echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    STG finished in $stg_elapsed secs"

          # Generate network.yaml config
          net_cfg="$TEMP_DIR/netcfg_${topology}_${model}_dp${dp}_tp${tp}_pp${pp}_ep${ep}_mb${micro_batch}.yml"
          topology_arr=()
          npus_arr=()
          bw_arr=()
          lat_arr=()

          # If HGX H100, use Switch + Ring topology
          if [ "$topology" = "hgx" ]; then
            # We want the Switch in HGX H100 to have no more than 8 NPUs, and then lower level rings to have 
            # higher dim than higher level rings because of oversubscription, so we do the following:
            
            # 1. sort the dimensions in descending order
            dims_arr=()
            [ $dp -gt 1 ] && dims_arr+=($dp)
            [ $tp -gt 1 ] && dims_arr+=($tp)
            [ $pp -gt 1 ] && dims_arr+=($pp)

            IFS=$'\n' sorted_dims=($(sort -nr <<<"${dims_arr[*]}"))
            unset IFS

            # 2. if largest dim >8, insert greatest dim that is <=8 at the front for the Switch
            if [ "${sorted_dims[0]}" -gt 8 ]; then
              found_insert=0
              for i in "${!sorted_dims[@]}"; do
                if [ "${sorted_dims[$i]}" -le 8 ]; then
                  # remove the found dim
                  dim_le8=${sorted_dims[$i]}
                  unset 'sorted_dims[i]'
                  # shift remaining elements and insert at front
                  sorted_dims=("$dim_le8" "${sorted_dims[@]}")
                  found_insert=1
                  break
                fi
              done

              # if all dims >8, skip
              if [ $found_insert -eq 0 ]; then
                echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    Skipping $topology $model dp=$dp tp=$tp pp=$pp"
                echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    Reason: all dims exceed 8 GPUs, cannot assign Switch"
                continue
              fi
            fi

            # first dim is Switch
            switch_np=${sorted_dims[0]}
            topology_arr+=("Switch")
            npus_arr+=("$switch_np")
            bw_arr+=(400)
            lat_arr+=(936.25)

            # remaining dims are Rings
            for ((i=1; i<${#sorted_dims[@]}; i++)); do
                ring_np=${sorted_dims[i]}
                topology_arr+=("Ring")
                npus_arr+=("$ring_np")
                bw_arr+=(50)
                lat_arr+=(1000)
            done
          elif [ "$topology" = "tpu" ]; then
            # For TPUv4, all dims are Rings
            dims_arr=()
            [ $dp -gt 1 ] && dims_arr+=($dp)
            [ $tp -gt 1 ] && dims_arr+=($tp)
            [ $pp -gt 1 ] && dims_arr+=($pp)

            # sort dims descending
            IFS=$'\n' sorted_dims=($(sort -nr <<<"${dims_arr[*]}"))
            unset IFS

            for dim_np in "${sorted_dims[@]}"; do
                topology_arr+=("Ring")
                npus_arr+=("$dim_np")
                bw_arr+=(50)
                lat_arr+=(1000)
            done
          else
            echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    Skipping $topology $model dp=$dp tp=$tp pp=$pp ep=$ep mb=$micro_batch"
            echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    Reason: topology $(topology) not supported"
            continue
          fi

          # Create arrays and write to network.yaml file
          topology_yaml="[ $(IFS=,; echo "${topology_arr[*]}") ]"
          npus_yaml="[ $(IFS=,; echo "${npus_arr[*]}") ]"
          bw_yaml="[ $(IFS=,; echo "${bw_arr[*]}") ]"
          lat_yaml="[ $(IFS=,; echo "${lat_arr[*]}") ]"

          cat > "$net_cfg" <<EOF
topology: $topology_yaml
npus_count: $npus_yaml
bandwidth: $bw_yaml
latency: $lat_yaml
EOF

          # Run ASTRA-sim
          echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    Running ASTRA-sim for $topology $model dp=$dp tp=$tp pp=$pp mb=$micro_batch"
          echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    Using system config: $sys_cfg"
          ASTRASIM_OUT="$OUTPUT_DIR/statistics/out_${topology}_${model}_dp${dp}_tp${tp}_pp${pp}_ep${ep}_mb${micro_batch}.txt"
          mkdir -p "$(dirname "$ASTRASIM_OUT")"
          echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    ASTRA-sim output will be written to $ASTRASIM_OUT"
          sim_start=$SECONDS
          (
            cd "$ASTRASIM_DIR" || exit
            "$ASTRASIM_BIN" \
              --workload-configuration="$trace_path/$trace_name" \
              --comm-group-configuration="$trace_path/$trace_name.json" \
              --system-configuration="$sys_cfg" \
              --network-configuration="$net_cfg" \
              --remote-memory-configuration="$remote_mem_cfg" \
              > "$ASTRASIM_OUT"
          )
          sim_elapsed=$(( SECONDS - sim_start ))
          echo "[sweep] [$(date '+%m-%d %H:%M:%S')]    ASTRA-sim finished in $sim_elapsed secs"

          # Clean up temp files
          rm -f "$net_cfg"
          rm -rf "$trace_path"

        done
      done
    done
  done
done
