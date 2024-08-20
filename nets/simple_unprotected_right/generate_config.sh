END_TIME=3600
REPEAT_PERIOD=10

netconvert \
  --node-files=netconfig/nodes.nod.xml \
  --edge-files=netconfig/edges.edg.xml \
  --connection-files=netconfig/connections.con.xml  \
  --tllogic-files=netconfig/tllogics.tll.xml \
  --output-file=simple_unprotected_right.net.xml

python $SUMO_HOME/tools/findAllRoutes.py \
  -n simple_unprotected_right.net.xml \
  -o routes.rou.xml \
  -s southJunction,westJunction \
  -t junctionEast,junctionNorth

duarouter \
  --net-file simple_unprotected_right.net.xml \
  --route-files vconfig/vtypes.rou.xml,routes.rou.xml,vconfig/vehicles.rou.xml \
  --output-file config.rou.xml

python $SUMO_HOME/tools/route/vehicle2flow.py config.rou.xml \
  -o simple_unprotected_right.rou.xml \
  -e $END_TIME -r $REPEAT_PERIOD

sumo \
  --net-file simple_unprotected_right.net.xml \
  --route-files simple_unprotected_right.rou.xml \
  --output-prefix "output/" \
  --statistic-output statistics.xml \
  --collision-output collisions.xml \
  --device.ssm.probability 1 \
  --device.ssm.file ssm.xml \
  --collision.action "teleport" \
  --collision.check-junctions true \
  --default.speeddev 0.1 \
  --random \
  --save-configuration sumo.config.xml \
 --save-commented true
