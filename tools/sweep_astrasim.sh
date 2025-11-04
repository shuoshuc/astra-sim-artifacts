#!/bin/bash

# --- Usage ---
# ./run_sweep.sh sys1d sys2d sys3d remote_mem.json [output_dir] [dp_values] [tp_values] [pp_values] [micro_batch_values] [models] [topology]
#
# Required arguments:
#   1: sys_cfg_1d (path)
#   2: sys_cfg_2d (path)
#   3: sys_cfg_3d (path)
#   4: remote_mem_cfg (path)
#
# Optional arguments:
#   5: output_dir (default: /app/examples/sweep_astrasim/)
#   6: dp_values (comma-separated, default: 1,2,4)
#   7: tp_values (comma-separated, default: 1,2,4)
#   8: pp_values (comma-separated, default: 1,2,4)
#   9: micro_batch_values (comma-separated, default: -1,16,32)
#   10: model_arg (comma-separated list, default: dense,gpt)
#   11: topology (default: tpu)

# --- Check required args ---
if [ $# -lt 4 ]; then
  echo "Usage: $0 sys1d sys2d sys3d remote_mem.json [output_dir] [dp_values] [tp_values] [pp_values] [micro_batch_values] [models] [topology]"
  exit 1
fi

# --- Required arguments ---
sys_cfg_1d=$1
sys_cfg_2d=$2
sys_cfg_3d=$3
remote_mem_cfg=$4

# --- Optional arguments ---
OUTPUT_DIR=${5:-"/app/examples/sweep_astrasim/"}
dp_arg=${6:-"1,2,4"}
tp_arg=${7:-"1,2,4"}
pp_arg=${8:-"1,2,4"}
micro_arg=${9:-"-1,16,32"}
model_arg=${10:-"dense,gpt"}
topology=${11:-"tpu"}

# --- Directories ---
ASTRASIM_DIR="/app/astra-sim"
STG_DIR="$ASTRASIM_DIR/symbolic_tensor_graph"
TEMP_DIR="$OUTPUT_DIR/temp"

mkdir -p "$OUTPUT_DIR"
mkdir -p "$TEMP_DIR"

# --- Convert comma-separated arguments into arrays ---
IFS=',' read -r -a dp_values <<< "$dp_arg"
IFS=',' read -r -a tp_values <<< "$tp_arg"
IFS=',' read -r -a pp_values <<< "$pp_arg"
IFS=',' read -r -a micro_batch_values <<< "$micro_arg"
IFS=',' read -r -a models <<< "$model_arg"

# --- Main loop ---
for model in "${models[@]}"; do
  for dp in "${dp_values[@]}"; do
    for tp in "${tp_values[@]}"; do
      for pp in "${pp_values[@]}"; do
        for micro_batch in "${micro_batch_values[@]}"; do
          echo "START $topology $model $dp $tp $pp $micro_batch $(date '+%Y-%m-%d %H:%M:%S')"

          ep=1
          npus_count=$((dp * tp * pp * ep))

          if [ "$npus_count" -eq 1 ] || [ "$npus_count" -gt 16384 ]; then
            echo "   Skipping $topology $model $dp $tp $pp $ep $micro_batch"
            continue
          fi

          dims=0
          [[ $dp -gt 1 ]] && ((dims++))
          [[ $tp -gt 1 ]] && ((dims++))
          [[ $pp -gt 1 ]] && ((dims++))
          [[ $ep -gt 1 ]] && ((dims++))

          case $dims in
              1) sys_cfg="$sys_cfg_1d" ;;
              2) sys_cfg="$sys_cfg_2d" ;;
              3) sys_cfg="$sys_cfg_3d" ;;
              *) echo "   Skipping: unsupported parallelism dimension count ($dims)"; continue ;;
          esac
          echo "   System config: $sys_cfg"

          trace_name="${topology}_${model}_${dp}_${tp}_${pp}_ep${ep}_mb${micro_batch}"
          trace_path="$TEMP_DIR/traces/$trace_name"
          mkdir -p "$trace_path"

          echo "   Gen trace, $npus_count, $dims"
          stg_start=$SECONDS
          (
            cd "$STG_DIR" || exit
            python main.py \
              --output_dir "$trace_path" \
              --output_name "$trace_name" \
              --model_type "$model" \
              --dp $dp --tp $tp --sp 1 --ep $ep --pp $pp \
              --micro_batch $micro_batch \
              --weight_sharded 0 \
              --chakra_schema_version v0.0.4
          )
          stg_elapsed=$(( SECONDS - stg_start ))
          echo "   STG: $stg_elapsed secs"

          # --- Network config generation ---
          net_cfg="$TEMP_DIR/netcfg_${topology}_${model}_dp${dp}_tp${tp}_pp${pp}_ep${ep}_mb${micro_batch}.yml"

          topology_arr=()
          npus_arr=()
          bw_arr=()
          lat_arr=()

          if [ "$topology" = "hgx" ]; then
            if [ "$dims" -eq 1 ]; then
              if [ "$npus_count" -gt 8 ]; then
                echo "   Skipping hgx dim 1"
                continue
              else
                topology_arr+=("Switch")
                npus_arr+=("$npus_count")
                bw_arr+=(400)
                lat_arr+=(936.25)
              fi
            else
              dims_arr=()
              [ $dp -gt 1 ] && dims_arr+=($dp)
              [ $tp -gt 1 ] && dims_arr+=($tp)
              [ $pp -gt 1 ] && dims_arr+=($pp)

              IFS=$'\n' sorted_dims=($(sort -nr <<<"${dims_arr[*]}"))
              unset IFS

              switch_np=${sorted_dims[0]}
              topology_arr+=("Switch")
              npus_arr+=("$switch_np")
              bw_arr+=(400)
              lat_arr+=(936.25)

              for ((i=1; i<${#sorted_dims[@]}; i++)); do
                  ring_np=${sorted_dims[i]}
                  topology_arr+=("Ring")
                  npus_arr+=("$ring_np")
                  bw_arr+=(50)
                  lat_arr+=(1000)
              done
            fi
          elif [ "$topology" = "tpu" ]; then
            dims_arr=()
            [ $dp -gt 1 ] && dims_arr+=($dp)
            [ $tp -gt 1 ] && dims_arr+=($tp)
            [ $pp -gt 1 ] && dims_arr+=($pp)

            for dim_np in "${dims_arr[@]}"; do
                topology_arr+=("Ring")
                npus_arr+=("$dim_np")
                bw_arr+=(50)
                lat_arr+=(1000)
            done
          else
            echo "   Skipping: unsupported topology ($topology)"
            continue
          fi

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

          # --- Run AstraSim ---
          echo "   Start AstraSim $topology $model $dp $tp $pp $ep $micro_batch"
          sim_start=$SECONDS
          (
            cd "$ASTRASIM_DIR" || exit
            ./build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware \
              --workload-configuration="$trace_path/$trace_name" \
              --comm-group-configuration="$trace_path/$trace_name.json" \
              --system-configuration="$sys_cfg" \
              --network-configuration="$net_cfg" \
              --remote-memory-configuration="$remote_mem_cfg" \
              > "$OUTPUT_DIR/out_${topology}_${model}_dp${dp}_tp${tp}_pp${pp}_ep${ep}_mb${micro_batch}.txt"
          )
          sim_elapsed=$(( SECONDS - sim_start ))
          echo "   AstraSim: $sim_elapsed secs"

          rm -f "$net_cfg"
          rm -rf "$trace_path"

        done
      done
    done
  done
done
