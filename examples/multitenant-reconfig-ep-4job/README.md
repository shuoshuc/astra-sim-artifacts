./run.sh <placement policy> <main job shapes> <torus size of X dim> <torus size of Y dim> <torus size of Z dim> <network bw GBps>

1.  ./run.sh random 2x2x1,2x2x1,2x2x1,2x2x1 4 4 1 50

    Job,JCT (nsec)
    J0,20266356082
    J1,20266435040
    J2,19570912402
    J3,17165325282


terminate called after throwing an instance of 'nlohmann::detail::parse_error'
  what():  [json.exception.parse_error.101] parse error at line 1, column 1: syntax error while parsing value - unexpected end of input; expected '[', '{', or a literal
./run.sh: line 83:  5082 Aborted                 (core dumped) ( ${ASTRA_SIM} --workload-configuration=${TRACE_PATH}/merged/trace --comm-group-configuration=${TRACE_PATH}/merged/comm_group.json --system-configuration=${INPUT_PATH}/sys.json --network-configuration=${INPUT_PATH}/network.yml --remote-memory-configuration=${INPUT_PATH}/RemoteMemory.json --circuit-schedules=${INPUT_PATH}/schedule.txt )
