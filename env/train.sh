export LIBSUMO_AS_TRACI=1

END_TIME=3600
REPEAT_PERIOD=10

netconvert --configuration-file ./nets/2lane_unprotected_right/2lane_unprotected_right.netccfg
python $SUMO_HOME/tools/findAllRoutes.py -n ./nets/2lane_unprotected_right/2lane_unprotected_right.net.xml -o ./nets/2lane_unprotected_right/routes.rou.xml -s southJunction,westJunction -t junctionEast,junctionNorth
duarouter ./nets/2lane_unprotected_right/2lane_unprotected_right.duarcfg
python $SUMO_HOME/tools/route/vehicle2flow.py ./nets/2lane_unprotected_right/config.rou.xml -o ./nets/2lane_unprotected_right/2lane_unprotected_right.rou.xml -e $END_TIME -r $REPEAT_PERIOD

python ./env/train.py
