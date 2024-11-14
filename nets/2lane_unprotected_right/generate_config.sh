END_TIME=3600
REPEAT_PERIOD=10
FRICTION="1.0"

#netconvert \
#  --node-files=netconfig/nodes.nod.xml \
#  --edge-files=netconfig/edges.edg.xml \
#  --connection-files=netconfig/connections.con.xml  \
#  --tllogic-files=netconfig/tllogics.tll.xml \
#  --output-file=simple_unprotected_right.net.xml

netconvert --configuration-file 2lane_unprotected_right.netccfg \
--default.friction $FRICTION

python $SUMO_HOME/tools/findAllRoutes.py \
  -n 2lane_unprotected_right.net.xml \
  -o routes.rou.xml \
  -s southJunction,westJunction \
  -t junctionEast,junctionNorth

#duarouter \
#  --net-file simple_unprotected_right.net.xml \
#  --route-files vconfig/vtypes.rou.xml,routes.rou.xml,vconfig/vehicles.rou.xml \
#  --output-file config.rou.xml

duarouter --configuration-file 2lane_unprotected_right.duarcfg

python $SUMO_HOME/tools/route/vehicle2flow.py config.rou.xml \
  -o 2lane_unprotected_right.rou.xml \
  -e $END_TIME -r $REPEAT_PERIOD

sumo \
  --net-file 2lane_unprotected_right.net.xml \
  --route-files 2lane_unprotected_right.rou.xml \
  --collision.action "teleport" \
  --collision.check-junctions true \
  --default.speeddev 0.1 \
  --random \
  --save-configuration 2lane_unprotected_right.sumocfg \
  --save-commented true
#  --output-prefix "NUL" \
#  --statistic-output statistics.xml \
#  --collision-output collisions.xml \
#  --device.ssm.probability 1 \
#  --device.ssm.file ssm.xml \
#  --device.ssm.measures "BR" \

mkdir -p output

echo "Done!"
