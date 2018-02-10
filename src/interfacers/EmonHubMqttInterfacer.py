"""class EmonHubMqttGenInterfacer

"""
import time
import paho.mqtt.client as mqtt
from emonhub_interfacer import EmonHubInterfacer
import Cargo

class EmonHubMqttInterfacer(EmonHubInterfacer):

    def __init__(self, name, mqtt_user=" ", mqtt_passwd=" ", mqtt_host="127.0.0.1", mqtt_port=1883):
        # Initialization
        super(EmonHubMqttInterfacer, self).__init__(name)

        # set the default setting values for this interfacer
        self._defaults.update({'datacode': '0'})
        self._settings.update(self._defaults)
        
        # Add any MQTT specific settings
        self._mqtt_settings = {
            # emonhub/rx/10/values format - default emoncms nodes module
            'node_format_enable': 1,
            'node_format_basetopic': 'emonhub/',
            
            # nodes/emontx/power1 format
            'nodevar_format_enable': 0,
            'nodevar_format_basetopic': "nodes/"
        }
        self._settings.update(self._mqtt_settings)
        
        self.init_settings.update({
            'mqtt_host':mqtt_host, 
            'mqtt_port':mqtt_port,
            'mqtt_user':mqtt_user,
            'mqtt_passwd':mqtt_passwd
        })

        self._connected = False          
                  
        self._mqttc = mqtt.Client()
        self._mqttc.on_connect = self.on_connect
        self._mqttc.on_disconnect = self.on_disconnect
        self._mqttc.on_message = self.on_message
        self._mqttc.on_subscribe = self.on_subscribe

    def _process_post(self, databuffer):
        if not self._connected:
            self._log.info("Connecting to MQTT Server")
            try:
                self._mqttc.username_pw_set(self.init_settings['mqtt_user'], self.init_settings['mqtt_passwd'])
                self._mqttc.connect(self.init_settings['mqtt_host'], self.init_settings['mqtt_port'], 60)
            except:
                self._log.info("Could not connect...")
                time.sleep(1.0)
            
        else:
            cargo = databuffer[0]
        
            # ----------------------------------------------------------
            # General MQTT format: emonhub/rx/emonpi/power1 ... 100
            # ----------------------------------------------------------
            if int(self._settings["nodevar_format_enable"])==1:
            
                # Node id or nodename if given
                nodestr = str(cargo.nodeid)
                if cargo.nodename!=False: nodestr = str(cargo.nodename)
                
                varid = 1
                for value in cargo.realdata:
                    # Variable id or variable name if given
                    varstr = str(varid)
                    if (varid-1)<len(cargo.names):
                        varstr = str(cargo.names[varid-1])
                    # Construct topic
                    topic = self._settings["nodevar_format_basetopic"]+nodestr+"/"+varstr
                    payload = str(value)
                    
                    self._log.debug("Publishing: "+topic+" "+payload)
                    result =self._mqttc.publish(topic, payload=payload, qos=2, retain=False)
                    
                    if result[0]==4:
                        self._log.info("Publishing error? returned 4")
                        # return False
                    
                    varid += 1
                    
                # RSSI
                topic = self._settings["nodevar_format_basetopic"]+nodestr+"/rssi"
                payload = str(cargo.rssi)
                self._log.info("Publishing: "+topic+" "+payload)
                result =self._mqttc.publish(topic, payload=payload, qos=2, retain=False)
            
            # ----------------------------------------------------------    
            # Emoncms nodes module format: emonhub/rx/10/values ... 100,200,300
            # ----------------------------------------------------------
            if int(self._settings["node_format_enable"])==1:
            
                topic = self._settings["node_format_basetopic"]+"rx/"+str(cargo.nodeid)+"/values"
                payload = ",".join(map(str,cargo.realdata))
                
                self._log.info("Publishing: "+topic+" "+payload)
                result =self._mqttc.publish(topic, payload=payload, qos=2, retain=False)
                
                if result[0]==4:
                    self._log.info("Publishing error? returned 4")
                    # return False
                    
                # RSSI
                topic = self._settings["node_format_basetopic"]+"rx/"+str(cargo.nodeid)+"/rssi"
                payload = str(cargo.rssi)
                
                self._log.info("Publishing: "+topic+" "+payload)
                result =self._mqttc.publish(topic, payload=payload, qos=2, retain=False)
                
                if result[0]==4:
                    self._log.info("Publishing error? returned 4")
                    # return False
                    
        return True

    def action(self):
        """

        :return:
        """
        self._mqttc.loop(0)

        # pause output if 'pause' set to 'all' or 'out'
        if 'pause' in self._settings \
                and str(self._settings['pause']).lower() in ['all', 'out']:
            return

        # If an interval is set, check if that time has passed since last post
        if int(self._settings['interval']) \
                and time.time() - self._interval_timestamp < int(self._settings['interval']):
            return
        else:
            # Then attempt to flush the buffer
            self.flush()
        
    def on_connect(self, client, userdata, flags, rc):
        
        connack_string = {0:'Connection successful',
                          1:'Connection refused - incorrect protocol version',
                          2:'Connection refused - invalid client identifier',
                          3:'Connection refused - server unavailable',
                          4:'Connection refused - bad username or password',
                          5:'Connection refused - not authorised'}

        if rc:
            self._log.warning(connack_string[rc])
        else:
            self._log.info("connection status: "+connack_string[rc])
            self._connected = True
            # Subscribe to MQTT topics
            self._mqttc.subscribe(str(self._settings["node_format_basetopic"])+"tx/#")
            
        self._log.debug("CONACK => Return code: "+str(rc))
        
    def on_disconnect(self, client, userdata, rc):
        if rc != 0:
            self._log.info("Unexpected disconnection")
            self._connected = False
        
    def on_subscribe(self, mqttc, obj, mid, granted_qos):
        self._log.info("on_subscribe")
        
    def on_message(self, client, userdata, msg):
        topic_parts = msg.topic.split("/")
        
        if topic_parts[0] == self._settings["node_format_basetopic"][:-1]:
            if topic_parts[1] == "tx":
                if topic_parts[3] == "values":
                    nodeid = int(topic_parts[2])
                    
                    payload = msg.payload
                    realdata = payload.split(",")
                    self._log.debug("Nodeid: "+str(nodeid)+" values: "+msg.payload)

                    rxc = Cargo.new_cargo(realdata=realdata)
                    rxc.nodeid = nodeid

                    if rxc:
                        # rxc = self._process_tx(rxc)
                        if rxc:
                            for channel in self._settings["pubchannels"]:
                            
                                # Initialize channel if needed
                                if not channel in self._pub_channels:
                                    self._pub_channels[channel] = []
                                    
                                # Add cargo item to channel
                                self._pub_channels[channel].append(rxc)
                                
                                self._log.debug(str(rxc.uri) + " Sent to channel' : " + str(channel))
                                
    def set(self, **kwargs):

        super (EmonHubMqttInterfacer, self).set(**kwargs)

        for key, setting in self._mqtt_settings.iteritems():
            #valid = False
            if not key in kwargs.keys():
                setting = self._mqtt_settings[key]
            else:
                setting = kwargs[key]
            if key in self._settings and self._settings[key] == setting:
                continue
            elif key == 'node_format_enable':
                self._log.info("Setting " + self.name + " node_format_enable: " + setting)
                self._settings[key] = setting
                continue
            elif key == 'node_format_basetopic':
                self._log.info("Setting " + self.name + " node_format_basetopic: " + setting)
                self._settings[key] = setting
                continue
            elif key == 'nodevar_format_enable':
                self._log.info("Setting " + self.name + " nodevar_format_enable: " + setting)
                self._settings[key] = setting
                continue
            elif key == 'nodevar_format_basetopic':
                self._log.info("Setting " + self.name + " nodevar_format_basetopic: " + setting)
                self._settings[key] = setting
                continue
            else:
                self._log.warning("'%s' is not valid for %s: %s" % (setting, self.name, key))
