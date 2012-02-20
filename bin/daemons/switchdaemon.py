#!/usr/local/bin/python

#######################
# TODO
# add vlan deletion by name
########################

import sys, os
#sys.path.append("/usr/local/hen/lib")
sys.path.append("/home/hen/u0/fhuici/development/svn/hen_scripts/lib")

import logging
import threading
import socket
import pickle
import commands
import re
import pydot
import traceback
from daemonizer import Daemonizer
from daemon import Daemon
from henmanager import HenManager
from auxiliary.daemonlocations import DaemonLocations
from auxiliary.hen import Port
from auxiliary.hen import VLAN, VlanOwner
from auxiliary.timer import GracefulTimer
from auxiliary.switchd.switchdb import SwitchDB
from auxiliary.switchd.workertask import *
from auxiliary.switchd.workerthread import *

logging.basicConfig()
log = logging.getLogger()
log.setLevel(logging.DEBUG)
class SNMPException(Exception):
    def __init__(self,message):
        Exception.__init__(self, message)
class PortNotInVlan(Exception):
    def __init__(self,message):
        Exception.__init__(self, message)
class VlanDoesNotExist(Exception):
    def __init__(self,message):
        Exception.__init__(self, message)
class NodeDoesNotExist(Exception):
    def __init__(self,message):
        Exception.__init__(self, message)
class InterfaceDoesNotExist(Exception):
    def __init__(self,message):
        Exception.__init__(self, message)

class SwitchControl(Daemon):
    """\brief Implements basic switch daemon functionality.
    """
    __version = "Switch Daemon v0.2 (simple)"
    __henManager = None
    __update_timer = None
    __update_lock = threading.Lock()
    
    __accept_connections = True
    __switchdb = None
    __nodeInstances = None
                                        
    def __init__(self):
        Daemon.__init__(self)
        # Initalise variables
        self.__henManager = HenManager()
        self.__nodes = None
        self.__vlans = {} # 
        self.__vlan_info = {} # switch_name -> [vlan_name,vlan_name,...]
        self.__switch_instances = {}
        self.__test_mode = False
        self.__minimum_id = 200
        self.__maximum_id = 2000
        self.__vlanOwnerFilename = "/usr/local/hen/etc/switchd/vlan_owner.dat"
        
        self.__int_to_vlan = {} # (computer_str,interface_str) -> vlan_name
        
        self.__switchdb = SwitchDB()
        log.debug("Switchdb "+str(self.__switchdb))
        # Register hen rpc methods and handlers
        log.debug("Registering methods")
        self.__registerMethods()
        # Load vlan info
        log.debug("Loading vlan info")
        self.__initaliseVlanInfo()
        # Setup mac polling
        log.debug("Loading henmanager")
        self.__switchdb.setHenManager(self.__henManager)
        log.debug("Loading links Db")
        self.__switchdb.loadLinksDb()
        log.debug("Initiating Nodes")
        self.initiateNodes()
        
        # vlan owners
        self.__vlan_owner_name = {}
        self.__vlan_name_owner = {}
        self.loadVlanOwnerFile()
        
            
    def __registerMethods(self):
        # hm commands
        self.registerMethodHandler("get_port_vlans_for_name", self.getPortVlansForName)
        self.registerMethodHandler("get_switch_port_vlans_for_name", self.getSwitchPortVlansForName)
        self.registerMethodHandler("get_vlan_for_name", self.getVlanForName)
        self.registerMethodHandler("get_vlan_for_user", self.getVlanForUser)
        self.registerMethodHandler("create_vlan_for_user", self.createVlanForUser)
        # older stuff

        self.registerMethodHandler("create_vlan_by_name", self.createVlanByName)
        self.registerMethodHandler("delete_vlan_by_name", self.deleteVlanByName)
        self.registerMethodHandler("add_port_to_vlan_by_name", self.addPortToVlanByName)
        self.registerMethodHandler("delete_port_from_vlan", self.deletePortFromVlan)
        self.registerMethodHandler("list_ports_on_vlan_on_switch", self.listPortsOnVlanOnSwitch)
        self.registerMethodHandler("list_vlans_on_switch", self.listVlansOnSwitch)
        self.registerMethodHandler("get_vlan_id_for_port", self.getVlanIdForPort)
        self.registerMethodHandler("get_vlan_name_for_port", self.getVlanNameForPort)
        # Testing code, might go away at any time
        #self.registerMethodHandler("get_next_free_vlan_id", self.getNextFreeVlanId)
        self.registerMethodHandler("add_port_to_vlan_by_id", self.addPortToVlanById)
        self.registerMethodHandler("enable_test_mode",self.enableTestMode)
        self.registerMethodHandler("disable_test_mode",self.disableTestMode)
        self.registerMethodHandler("clear_vlans", self.clearVlans)
        self.registerMethodHandler("list_empty_vlans_on_switch",self.listEmptyVlansOnSwitch)
        self.registerMethodHandler("clear_empty_vlans_on_switch",self.clearEmptyVlansOnSwitch)

    # HM COMMANDS  ########################################

    def createVlanForUser(self,prot,seq,ln,payload):
        args = pickle.loads(payload)
        if len(args) != 2:
            code = 400
            reply = str("Incorrect number of arguments")
            self.__sendReply(prot,code,seq,reply)
            return
        vlan_str = args[0]
        user_str = args[1]
        try:
            for vlan_owner in self.__vlan_owner_name:
                print vlan_owner
            
            code = 200
            v = VlanOwner(vlan_str,user_str)
            self.__vlan_owners.append(v)
            reply = str("Trying to create ")+str(v)
            self.__sendReply(prot,code,seq,reply)
            return
                                            
        except Exception, e:
            code = 400
            reply = "Error with createVlanForUser "+str(e)
            self.__sendReply(prot,code,seq,reply)
            return
                                

    # getPortVlansForName  ########################################
    def getPortVlansForName(self,prot,seq,ln,payload):
        args = pickle.loads(payload)
        if len(args) != 2:
            code = 400
            reply = str("Incorrect number of arguments")
            self.__sendReply(prot,code,seq,reply)
            return
                            
        computer_str = args[0]
        interface_str = args[1]
        try:
            (computer, switch_str, switch, switch_obj, port_str) = self.__getDeviceObjects(computer_str, interface_str)
            reply = self.__get_port_info(switch_obj,switch_str,port_str)
                       
            code = 200
            self.__sendReply(prot,code,seq,reply)
        except Exception, e:
            code = 400
            reply = "Error with getPortVlansForName "+str(e)
            self.__sendReply(prot,code,seq,reply)
            return

    # getVlanForName  ########################################
    def getVlanForName(self,prot,seq,ln,payload):
        vlan_str = pickle.loads(payload)
        if vlan_str == None:
            code = 400
            reply = str("Incorrect argument")+" "+str(vlan_str)
            self.__sendReply(prot,code,seq,reply)
            return
        
        try:
            reply = self.__get_vlan_info(vlan_str)
                       
            code = 200
            self.__sendReply(prot,code,seq,reply)
        except Exception, e:
            code = 400
            reply = "Error with getVlanForName "+str(e)
            self.__sendReply(prot,code,seq,reply)
            return

    # getVlanForUser  ########################################
    def getVlanForUser(self,prot,seq,ln,payload):
        user_str = pickle.loads(payload)
        
        reply = ""
        try:
            for vlan in self.__vlan_owner_name[user_str]:
                reply = reply + " " + str(vlan.getName())
            code = 200
            self.__sendReply(prot,code,seq,reply)
        except Exception, e:
            code = 400
            reply = "Error with getPortVlansForName "+str(e)
            self.__sendReply(prot,code,seq,reply)
            return

    def loadVlanOwnerFile(self):
        f = open(self.__vlanOwnerFilename,'r')
        
        for l in f.readlines():
            v = VlanOwner()
            v.fromFileString(l.rstrip('\n'))
            if not self.__vlan_owner_name.has_key(v.getOwner()):
                self.__vlan_owner_name[v.getOwner()] = []
            self.__vlan_owner_name[v.getOwner()].append(v)
            self.__vlan_name_owner[v.getName()] = v
            f.close()
        

    def saveVlanOwnerFile(self,vlans):
        f = open(self.__vlanOwnerFilename,'w')
        for v in self.__name_owner:
            f.write(v.toFileString()+"\n")
        f.close()

    # OLDER STUFF  ########################################

    # Add Port to Vlan by Name ################################################
    def addPortToVlanByName(self,prot,seq,ln,payload):
        args = pickle.loads(payload)
        if len(args) != 3:
            code = 400
            reply = str("Incorrect number of arguments")
            self.__sendReply(prot,code,seq,reply)
            return        
        computer_str = args[0]
        interface_str = args[1]
        vlan_str = args[2]
        try:
            (code,reply) = self.__addPortToVlan(computer_str,interface_str,vlan_str,None)
        except Exception, e:
            code = 400
            reply = "Error with addPortToVlanByName "+str(e)
            traceback.print_exc(file=sys.stdout)
            self.__sendReply(prot,code,seq,reply)
            return
        self.__sendReply(prot,code,seq,reply)
        
    def __addPortToVlan(self, computer_str, interface_str, vlan_str, vlan_id):
        (computer, switch_str, switch, switch_obj, port_str) = self.__getDeviceObjects(computer_str, interface_str)
        (vlan_name,old_vlan_id,port_obj) = self.__findVlanOfPort(switch_obj,switch_str,port_str)
        
        if (old_vlan_id != 1):
            log.info("need to delete this port")
            (code, reply) = self.__deletePortFromVlan(computer_str, interface_str, vlan_name)

        if (self.__vlans[switch_str] == None):
            try:
                self.__vlans[switch_str] = switch_obj.getFullVLANInfo()
            except Exception, e:
                raise SNMPException("Snmp exception getFullVLANInfo from switch"+str(switch_str)) 
            
        if (vlan_str != None):
            # adding by vlan string
            if not self.__switchHasVlanByName(vlan_str,switch_str):
                self.__createNewVlanByName(vlan_str,switch_obj,switch_str)
        else:
            log.info("Adding vlan based on vlan id "+str(vlan_id)+" on switch "+str(switch_str))
            if not self.__switchHasVlanById(vlan_id,switch_str):
                self.__createNewVlanById(vlan_id,switch_obj,switch_str)
                vlan_str = self.__getVlanNameFromId(switch_str,vlan_id)
        try:
            result = switch_obj.addPorts(vlan_str,[Port(port_str,False,port_str)])
        except Exception, e:
            raise SNMPException("Snmp exception addPorts from switch"+str(switch_str)) 
        
        if result == 0:
            # write to log file ?
            log.info("Added port "+str(port_str)+" to vlan "+str(vlan_str))
            code = 200       
            reply = "success"
        else:
            log.critical("Failed to add port "+str(port_str)+" to vlan "+str(vlan_str))
            code = 400
            reply = "failure"    
        return (code,reply)

    # Delete Port From Vlan ################################################
    def deletePortFromVlan(self,prot,seq,ln,payload):
        args = pickle.loads(payload)
        if len(args) != 3:
            code = 400
            reply = str("Incorrect number of arguments")
            self.__sendReply(prot,code,seq,reply)
            return        
        computer_str = args[0]
        interface_str = args[1]
        vlan_str = args[2]
        try:
            (code,reply) = self.__deletePortFromVlan(computer_str, interface_str, vlan_str)
            self.__sendReply(prot,code,seq,reply)
            return
        except Exception, e:
            code = 400
            reply = "Error with deletePortFromVlan "+str(e)
            self.__sendReply(prot,code,seq,reply)
            return

    def __deletePortFromVlan(self, computer_str, interface_str, vlan_str):
        (computer, switch_str, switch, switch_obj, port_str) = self.__getDeviceObjects(computer_str, interface_str)
        #log.debug("Trying to delete port from vlan "+str(switch_str)+" "+ str( port_str))
        try:
            vlans = switch_obj.getFullVLANInfo()
        except Exception, e:
            raise SNMPException("Snmp exception getFullVlanInfo from switch"+str(switch_str))
        
        vlan = None
        vlan_found = False
        for v in vlans:
            if v.getName() == vlan_str:
                vlan = v
                vlan_found = True
                break
            
        if not vlan_found:
            raise VlanDoesNotExist("Vlan "+str(vlan_str)+" does not exist.")
        
        ports = vlan.getPortsOnSwitch(switch_str)
        port_found = False
        for p in ports:
            if str(p.getPortNumber()) == port_str:
                port_found = True
                break
            
        if port_found:
            try:
                result = switch_obj.deletePorts(vlan.getName(),[Port(port_str,False,port_str)])
            except Exception, e:
                raise SNMPException("Snmp exception deletePorts from switch"+str(switch_str)) 
        else:
            raise PortNotInVlan("Port "+str(port_str)+" not in vlan "+str(vlan_str))
        
        if result == 0:
            # write to log file ?
            log.info("Deleted port "+str(port_str)+" from vlan "+str(vlan_str))
            code = 200       
            reply = "success"
        else:
            log.critical("Failed to delete port "+str(port_str)+" from vlan "+str(vlan_str))
            code = 400
            reply = "failure"    
        return (code,reply)
    
    # List Ports on Vlan on Switch ########################################

    def listPortsOnVlanOnSwitch(self,prot,seq,ln,payload):
        args = pickle.loads(payload)
        if len(args) != 2:
            code = 400
            reply = str("Incorrect number of arguments")
            self.__sendReply(prot,code,seq,reply)
            return        
        switch_str = args[0]
        vlan_str = args[1]
        try:
            switch_obj = self.__getSwitchInstance(switch_str)
            vlan_obj = switch_obj.getFullVLANInfo(vlan_str)
        except Exception, e:
            code = 400
            reply = "Error with listPortsOnVlanOnSwitch "+str(e)
            self.__sendReply(prot,code,seq,reply)
            return
        
        reply = ""
        for i in vlan_obj:
            reply += str(i)
        code = 200
        self.__sendReply(prot,code,seq,reply)
        retur                                               
    # List Vlans on Switch ########################################

    def listVlansOnSwitch(self,prot,seq,ln,payload):
        args = pickle.loads(payload)
        if len(args) != 1:
            code = 400
            reply = str("Incorrect number of arguments")
            self.__sendReply(prot,code,seq,reply)
            return
        switch_str = args[0]
        try:
            switch_obj = self.__getSwitchInstance(switch_str)
        except Exception, e:
            code = 400
            reply = "Error with listVlansOnSwitch "+str(e)
            self.__sendReply(prot,code,seq,reply)
            return
        try:
            vlan_obj = switch_obj.getFullVLANInfo()
        except Exception, e:
            code = 400
            reply = "Error with listVlansOnSwitch "+str(e)
            self.__sendReply(prot,code,seq,reply)
            return
        
        reply = ""
        for i in vlan_obj:
            vlan_name = self.__rewriteVlan(i.getName())
            reply += str(vlan_name)+" "+str(i.getID())+"\n"
        code = 200
        self.__sendReply(prot,code,seq,reply)
                                                                    
    # get Vlan Id For Port ########################################
    def getVlanIdForPort(self,prot,seq,ln,payload):
        args = pickle.loads(payload)
        if len(args) != 2:
            code = 400
            reply = str("Incorrect number of arguments")
            self.__sendReply(prot,code,seq,reply)
            return
                            
        computer_str = args[0]
        interface_str = args[1]
        try:
            
            (computer, switch_str, switch, switch_obj, port_str) = self.__getDeviceObjects(computer_str, interface_str)
            #(vlan_name,vlan_id,port_obj) = self.__findVlanOfPort_new(switch_obj,switch_str,port_str)
            reply = self.__get_port_info(switch_obj,switch_str,port_str)
                       
            code = 200
            self.__sendReply(prot,code,seq,reply)
        except Exception, e:
            code = 400
            reply = "Error with getVlanIdForPort "+str(e)
            self.__sendReply(prot,code,seq,reply)
            return

    # get Vlan Id For Switch Port ########################################
    def getSwitchPortVlansForName(self,prot,seq,ln,payload):
        args = pickle.loads(payload)
        if len(args) != 2:
            code = 400
            reply = str("Incorrect number of arguments")
            self.__sendReply(prot,code,seq,reply)
            return
                            
        switch_str = args[0]
        port_str = args[1]
        try:
            
            
            (switch,switch_obj) = self.__getSwitchInstance(switch_str)
            
            reply = self.__get_port_info(switch_obj,switch_str,port_str)
                       
            code = 200
            self.__sendReply(prot,code,seq,reply)
        except Exception, e:
            code = 400
            reply = "Error with getVlanIdForSwitchPort "+str(e)
            self.__sendReply(prot,code,seq,reply)
            return
        
    # get Vlan Name For Port ########################################        
    def getVlanNameForPort(self,prot,seq,ln,payload):
        args = pickle.loads(payload)
        if len(args) != 2:
            code = 400
            reply = str("Incorrect number of arguments")
            self.__sendReply(prot,code,seq,reply)
            return
                            
        computer_str = args[0]
        interface_str = args[1]
        try:
            if self.__int_vlan_map.has_key((computer_str, interface_str)):
                vlan_name = self.__int_vlan_map((computer_str, interface_str))
            else:
                (computer, switch_str, switch, switch_obj, port_str) = self.__getDeviceObjects(computer_str, interface_str)
                (vlan_name,vlan_id,port_obj) = self.__findVlanOfPort(switch_obj,switch_str,port_str)
            code = 200
            reply = str(vlan_name)
            self.__sendReply(prot,code,seq,reply)
        except Exception, e:
            code = 400
            reply = "Error with getVlanNameForPort "+str(e)
            self.__sendReply(prot,code,seq,reply)
            return
        
    # create New Vlan By Name ########################################        
    def createVlanByName(self,prot,seq,ln,payload):
         args = pickle.loads(payload)
         if len(args) != 2:
             code = 400
             reply = str("Incorrect number of arguments")
             self.__sendReply(prot,code,seq,reply)
             return
         vlan_str = args[0]
         switch_str = args[1]
         try:
              (switch,switch_obj) = self.__getSwitchInstance(switch_str)
              if not self.__switchHasVlanByName(vlan_str,switch_str):
                  result = self.__createNewVlanByName(vlan_str,switch_obj,switch_str)
                  if result == 0:
                      reply = "vlan "+str(vlan_str)+" created on switch "+str(switch_str)
                      code = 200
                  else:
                      reply = "failed to create vlan "+str(vlan_str)+" on switch "+str(switch_str)
                      code = 400
              else:
                  reply = "vlan "+str(vlan_str)+" already exists on switch "+str(switch_str)
                  code = 400
         except Exception, e:
             code = 400
             reply = "Error with createNewVlanByName "+str(e)
             self.__sendReply(prot,code,seq,reply)
             return
         self.__sendReply(prot,code,seq,reply)
         return                                                                    

    def __createNewVlanByName(self,vlan_str,switch_obj,switch_str):
        log.info("Creating new vlan "+str(vlan_str)+" on "+str(switch_str))
        switches = {}
        switches[switch_str] = []
        v = VLAN(vlan_str,switches,self.__getNextFreeVlanId(switch_str))
        result = switch_obj.createVLAN(v)
        self.__reload_vlan_info(switch_str,switch_obj)
        log.info("result from create vlan "+str(result))
        return result

    # delete New Vlan By Name ########################################        

    def deleteVlanByName(self,prot,seq,ln,payload):
         args = pickle.loads(payload)
         if len(args) != 2:
             code = 400
             reply = str("Incorrect number of arguments")
             self.__sendReply(prot,code,seq,reply)
             return
         vlan_str = args[0]
         switch_str = args[1]
         try:
              (switch,switch_obj) = self.__getSwitchInstance(switch_str)
              if self.__switchHasVlanByName(vlan_str,switch_str):
                  result = self.__deleteVlan(vlan_str,switch_obj,switch_str)
                  if result == 0:
                      reply = "vlan "+str(vlan_str)+" deleted from switch "+str(switch_str)
                      code = 200
                  else:
                      reply = "failed to delete vlan "+str(vlan_str)+" on switch "+str(switch_str)
                      code = 400
              else:
                  reply = "vlan "+str(vlan_str)+" does not exists on switch "+str(switch_str)
                  code = 400
         except Exception, e:
             code = 400
             reply = "Error with deleteVlanByName "+str(e)
             traceback.print_exc(file=sys.stdout)
             self.__sendReply(prot,code,seq,reply)
             return
         self.__sendReply(prot,code,seq,reply)
         return                                                                    

    def __deleteVlan(self,vlan_str,switch_obj,switch_str):
        log.info("Deleting vlan "+str(vlan_str)+" on "+str(switch_str))
        self.__reload_vlan_info(switch_str,switch_obj)
        result = switch_obj.deleteVLAN(vlan_str)
        self.__reload_vlan_info(switch_str,switch_obj)
        log.info("result from vlan "+str(result))


    
    # Old stuff
  
    def __initaliseVlanInfo(self):
        if self.__nodes == None:
            self.__getNodes()
        for node_type in self.__nodes:
            if node_type == "switch":
                for node in self.__nodes[node_type]:
                    # Gets switch objects and basic info
                    if str(self.__nodes[node_type][node].getNodeID()) == "switch14":
                        log.debug("Getting switch instance for "+str(self.__nodes[node_type][node].getNodeID()))
                        (switch,switch_obj) = self.__getSwitchInstance(self.__nodes[node_type][node].getNodeID())
                        self.__reload_vlan_info(switch.getNodeID(),switch_obj)
                    
    def __sendReply(self,prot,code,seq,payload):
        if (code == 0):
            code = 200
        else:
            code = 422 # returnCodes[422] = "error executing command"
        prot.sendReply(code, seq, payload)

    def __getNodes(self):
        self.__nodes = self.__henManager.getNodes("all")

    def __getComputer(self, computer_str):
        if self.__nodes == None:
            self.__getNodes()
        for node_type in self.__nodes:
            for node in self.__nodes[node_type]:
                if self.__nodes[node_type][node].getNodeID() == computer_str:
                    return self.__nodes[node_type][node]
        raise NodeDoesNotExist("Node "+str(computer_str)+" does not exist.")

    def __getSwitchLocation(self, computer, interface_str):
        interfaces = computer.getInterfaces()
        for interface_type in interfaces:
            for iface in interfaces[interface_type]:
                if iface.getInterfaceID() == interface_str:
                    return (iface.getSwitch(), iface.getPort())
        raise InterfaceDoesNotExist("Interface "+str(interface_str)+" does not exist on "+str(computer.getNodeID()))

    def __rewriteVlan(self,vlan):
        if vlan == "Default VLAN" or vlan == "DEFAULT_VLAN" or vlan == "Vlan 1" or vlan == "default":
            return "Default"
        return vlan
    
    def __reload_vlan_info(self, switch_str, switch_obj):
        self.__vlan_info[switch_str] = switch_obj.getVlanInfo()
        if self.__vlan_info[switch_str] == None:
            print "ERRROR no vlan content for switch",switch_str
        for i in self.__vlan_info[switch_str]:
            print i,self.__vlan_info[switch_str][i]

    def enableTestMode(self,prot,seq,ln,payload):
        self.__test_mode = True
        self.__minimum_id = 20
        self.__maximum_id = 30
        code = 200
        self.__sendReply(prot,code,seq,"")

    def disableTestMode(self,prot,seq,ln,payload):
        self.__test_mode = False
        self.__minimum_id = 200
        self.__maximum_id = 2000
        code = 200
        self.__sendReply(prot,code,seq,"")
    
    def clearVlans(self,prot,seq,ln,payload):
        (switch_str) = pickle.loads(payload)
        (switch,switch_obj) = self.__getSwitchInstance(switch_str)
        
        
        for i in self.__vlan_info[switch_str]:
            if self.__vlan_info[switch_str][i][0] < self.__minimum_id:
                pass
            elif self.__vlan_info[switch_str][i][0] > self.__maximum_id:
                pass
            else:
                log.info("Deleting vlan "+str(i)+" on "+str(switch_str))
                self.__deleteVlan(i,switch_obj,switch_str)
        code = 200
        self.__sendReply(prot,code,seq,"")

    def __findVlanOfPort(self,switch_obj,switch_str,port_str):
        vlans = switch_obj.getFullVLANInfo()
        for vlan in vlans:
            ports = vlan.getPortsOnSwitch(switch_str)
            for port in ports:
                if str(port.getPortNumber()) == port_str:
                    return (vlan.getName(),vlan.getID(),port)
        return (None,None)

    def __get_vlan_info(self,vlan_str):
        res = ""
        if self.__nodes == None:
            self.__getNodes()
        for node_type in self.__nodes:
            if node_type == "switch":
                for node in self.__nodes[node_type]:
                    # Gets switch objects and basic info
                    (switch,switch_obj) = self.__getSwitchInstance(self.__nodes[node_type][node].getNodeID())
                    try:
                        switch_obj.refreshVlanInfo()
                        ports = switch_obj.getPorts()
                        output = switch_obj.getVlanByName(vlan_str)
                        if output != None:
                            res += str(output.toString(ports))
                    except:
                        pass
        if res == "" :
            return "Unknown vlan"
        return str(res)

    def __get_port_info(self,switch_obj,switch_str,port_str):
        switch_obj.refreshVlanInfo()
        res = switch_obj.getPortByName(port_str)
        if res == None :
            return "Unknown Port"
        return str(res)

    def addPortToVlanById(self,prot,seq,ln,payload):
        (computer_str, interface_str, vlan_id) = pickle.loads(payload)
        log.info("trying to use vlan id "+str(vlan_id))
        (code,reply) = self.__addPortToVlan(computer_str,interface_str,None,int(vlan_id))
        self.__sendReply(prot,code,seq,reply)
    
    def __switchHasVlanByName(self,vlan_str,switch_str):
        log.info("checking if "+str(switch_str)+" has vlan "+str(vlan_str))
        if self.__vlan_info[switch_str] == None:
            (switch, switch_obj) =  self.__getSwitchInstance(switch_str)
            self.__reload_vlan_info(switch.getNodeID(),switch_obj)
        
        for vlan in self.__vlan_info[switch_str]:
            if vlan == vlan_str:
                log.info(str(switch_str)+" does have vlan "+str(vlan_str))
                return True
        log.info(str(switch_str)+" does not have vlan "+str(vlan_str))
        return False

    def __getVlanNameFromId(self,switch_str,vlan_id):
         log.info("getting vlan name from id "+str(vlan_id)+" on switch "+str(switch_str))
         for vlan in self.__vlans[switch_str]:
             if vlan.getID() == vlan_id:
                 log.info(str(switch_str)+" does have vlan id "+str(vlan_id)+" name is "+str(vlan.getName()))
                 return vlan.getName()
         log.info(str(switch_str)+" does not have name for vlan id "+str(vlan_id))
         raise VlanDoesNotExist("no vlan for id "+str(vlan_id)+" on switch "+str(switch_str))
                                                         

    def __switchHasVlanById(self,vlan_id,switch_str):
        log.info("checking if "+str(switch_str)+" has vlan id "+str(vlan_id))
        for vlan in self.__vlans[switch_str]:
            if vlan.getID() == vlan_id:
                log.info(str(switch_str)+" does have vlan id "+str(vlan_id))
                return True
        log.info(str(switch_str)+" does not have vlan id "+str(vlan_id))
        return False    

    def testGetNextFreeVlanId(self,prot,seq,ln,payload):
        (switch_str) = pickle.loads(payload)
        code = 200
        reply = self.__getNextFreeVlanId(switch_str)
        self.__sendReply(prot,code,seq,str(reply))

    def __getNextFreeVlanId(self,switch_str=None):
        log.info("Getting next free vlan id")
        vlan_id_list = []
        #self.__minimum_id = 20
        #self.__maximum_id = 30
        last = self.__minimum_id
        if switch_str != None:
            for i in self.__vlan_info[switch_str]:
                if self.__vlan_info[switch_str][i][0] < self.__minimum_id:
                    pass
                elif self.__vlan_info[switch_str][i][0] > self.__maximum_id:
                    pass
                else:
                    vlan_id_list.append(self.__vlan_info[switch_str][i][0])
        else:
            for switch_str in self.__vlan_info:
                for i in self.__vlan_info[switch_str]:
                    if self.__vlan_info[switch_str][i][0] < self.__minimum_id:
                        pass
                    elif self.__vlan_info[switch_str][i][0] > self.__maximum_id:
                        pass
                    else:
                        vlan_id_list.append(self.__vlan_info[switch_str][i][0])
                        
        vlan_id_list.sort()
        
        for i in vlan_id_list:
#            print i
            if last+1 < i:
                log.info("Next free vlan id is "+str(last+1))
                return last+1
            last = i
        log.info("Next free vlan id is "+str(self.__minimum_id)+" min id")
        return self.__minimum_id
        

    def __createNewVlanById(self,vlan_id,switch_obj,switch_str):
        log.info("Creating new id "+str(vlan_id)+" on "+str(switch_str))
        switches = {}
        switches[switch_str] = []
        v = VLAN(None,switches,vlan_id)
        result = switch_obj.createVLAN(v)
        self.__reload_vlan_info(switch_str,switch_obj)
        log.info("result from create vlan id "+str(vlan_id)+" on switch "+str(switch_str)+" is "+str(result))

    def __getVlanId(self,vlan_str,switch_str):
        return self.__vlan_info[switch_str][vlan_str][0]

    def listEmptyVlansOnSwitch(self,prot,seq,ln,payload):
        (switch_str) = pickle.loads(payload)
        (switch,switch_obj) = self.__getSwitchInstance(switch_str)
        if switch == None:
            code = 400
            reply = "No such switch "+switch_str
            self.__sendReply(prot,code,seq,reply)
            return
        vlan_obj = (switch_obj.getFullVLANInfo())
        reply = ""
        for i in vlan_obj:
            if len(i.getPortsOnSwitch(switch_str)) == 0:
                vlan_name = self.__rewriteVlan(i.getName())
                reply += str(vlan_name)+" "+str(i.getID())+"\n"
        code = 200
        self.__sendReply(prot,code,seq,reply)

    def clearEmptyVlansOnSwitch(self,prot,seq,ln,payload):
        (switch_str) = pickle.loads(payload)
        (switch,switch_obj) = self.__getSwitchInstance(switch_str)
        if switch == None:
            code = 400
            reply = "No such switch "+switch_str
            self.__sendReply(prot,code,seq,reply)
            return
        vlan_obj = (switch_obj.getFullVLANInfo())
        reply = "Deleted the following empty vlans\n"
        for i in vlan_obj:
            if len(i.getPortsOnSwitch(switch_str)) == 0:
                vlan_name = self.__rewriteVlan(i.getName())
                reply += str(vlan_name)+" "+str(i.getID())+"\n"
                log.info("Deleting vlan "+str(i.getID())+" on "+str(switch_str))
                self.__deleteVlan(str(i.getName()),switch_obj,switch_str)
                                                
        code = 200
        self.__sendReply(prot,code,seq,reply)


    def initiateNodes(self):
        """\brief Creates a {nodeid:(node,nodeinstance)} dictionary for sensor
        readings, and a {nodeid:node} dictionary for host ping checking.
        """
        log.debug("Creating NodeInstance map")
        self.__nodeInstances = {}
        
        nodes = self.__henManager.getNodes("all", "all")
        
        for nodeType in nodes.keys():
            if nodeType != "switch" :
                continue
            nodeTypes = nodes[nodeType]
            for node in nodeTypes.values():
                if node.getStatus() == "dead" or node.getStatus() == "maintanence" :
                    continue
#                elif node.getNodeID() != "switch14" :
#                    continue
        
                
                try:
                    self.__nodeInstances[node.getNodeID()] = \
                                                           (node, node.getInstance())
                    log.debug("Created instance for node [%s]" % \
                              str(node.getNodeID()))
                except Exception, e:
                    log.debug("Creating node instance failed for node [%s]: %s" % (str(node.getNodeID()), str(e)))
        log.debug("initiateNodes() completed. NodeInstances[%s]" % (str(len(self.__nodeInstances.keys()))))
        counter = 0
        for nodeid in self.__nodeInstances.keys():
            log.debug("[%s] %s" % (str(counter), nodeid))
            counter += 1

    
    ## Internal methods
        
    def acceptingConnections(self):
        """\brief To question whether the daemon is accepting connections"""
        return self.__accept_connections
    
    def setDBDirectory(self, dbDir):
        self.__switchdb.setDBDirectory(dbDir)
        
    ## Library functions

    # Given a switch name, return a switch object
    def __getSwitchInstance(self,switch_str):
        if self.__switch_instances.has_key(switch_str):
            return self.__switch_instances[switch_str]
        if self.__nodes == None:
            self.__getNodes()
        for node_type in self.__nodes:
            for node in self.__nodes[node_type]:
                if self.__nodes[node_type][node].getNodeID() == switch_str:
                    switch = self.__nodes[node_type][node]
                    if (switch.getStatus() == "operational" ): #and switch_str =="switch14"):
                        switch_obj = switch.getInstance()
                    else:
                        log.debug("Not creating an instance of "+str(switch_str))
                        return (None,None)
                    self.__switch_instances[switch_str] = (switch,switch_obj)
                    if not self.__vlans.has_key(switch_str):
                        self.__vlans[switch_str] = None
                        try:
                            self.__vlan_info[switch_str] = switch_obj.getVlanInfo()
                        except:
                            pass
                    return (switch, switch_obj)
        return (None,None)

    def __getDeviceObjects(self,computer_str, interface_str):
        computer = self.__getComputer(computer_str)
                
        if computer == None:
            log.info("Computer "+str(computer_str)+" doesn't exist.")
            return (None, None, None, None, None)

        (switch_str, port_str) = self.__getSwitchLocation(computer,interface_str)
        if switch_str == "":
            log.info("Switch not found for computer "+str(computer_str)+" interface "+str(interface_str))
            return (None, None, None, None, None)
        
        (switch, switch_obj) = self.__getSwitchInstance(switch_str)
        
        if switch_obj == None:
            log.info("Can't create switch instance for "+str(switch_str))
            return (None, None, None, None, None)

        return (computer, switch_str, switch, switch_obj, port_str)


    def stopDaemon(self,prot,seq,ln,payload):
        """\brief Stops the daemon and all threads
        This method will first stop any more incoming queries, then wait for
        any update tasks to complete, before stopping itself.
        """
        log.info("stopDaemon called.")
        prot.sendReply(200, seq, "Accepted stop request.")
        log.debug("Sending stopDaemon() response")
        self.acceptConnections(False)
        log.debug("Attempting to acquire update lock")
        self.__update_lock.acquire()
        log.debug("Stopping update timer")
        self.__update_timer.stop()
        log.debug("Releasing update lock")
        self.__update_lock.release()
        log.info("Stopping SwitchDaemon (self)")
        self.stop()

class SwitchDaemon(Daemonizer):
    """\brief Creates sockets and listening threads, runs main loop"""
    __bind_addr = DaemonLocations.switchDaemon[0]
    __port = DaemonLocations.switchDaemon[1]
    __sockd = None
    __switchcontrol = None

    def __init__(self, doFork):
        Daemonizer.__init__(self, doFork)

    def run(self):
        self.__sockd = socket.socket(socket.AF_INET,socket.SOCK_STREAM,0)
        log.debug("Binding to port: " + str(self.__port))
        self.__sockd.bind((self.__bind_addr, self.__port))
        log.info("Listening on " + str(self.__bind_addr) + ":" + str(self.__port))
        self.__sockd.listen(10)
        self.__sockd.settimeout(2) # 2 second timeouts
        log.debug("Creating SwitchDaemon")
        self.__switchcontrol = SwitchControl()
        log.debug("Starting DB")
        self.__switchcontrol.setDBDirectory(self.__switch_db_dir)
        #self.__switchcontrol.startDB()
        #self.__switchcontrol.startUpdateTimers()
        log.info("Starting SwitchDaemon")
        self.__switchcontrol.start()
        while self.__switchcontrol.isAlive():
            if self.__switchcontrol.acceptingConnections():
                # allow timeout of accept() to avoid blocking a shutdown
                try:
                    (s,a) = self.__sockd.accept()
                    log.debug("New connection established from " + str(a))
                    self.__switchcontrol.addSocket(s)
                except:
                    pass
            else:
                log.warning(\
                      "SwitchDaemon still alive, but not accepting connections")
                time.sleep(2)
        log.debug("Closing socket.")
        self.__sockd.shutdown(socket.SHUT_RDWR)
        self.__sockd.close()
        while threading.activeCount() > 1:
            cThreads = threading.enumerate()
            log.warning("Waiting on " + str(threading.activeCount()) + \
                        " active threads...")
            time.sleep(2)
        log.info("SwitchDaemon Finished.")
        # Now everything is dead, we can exit.
        sys.exit(0)

    def setDBDirectory(self, dbDir):
        self.__switch_db_dir = dbDir
                    

def main():
    """\brief Creates, configures and runs the main daemon
    TODO: Move config variables to main HEN config file.
    """
    WORKDIR = '/var/hen/switchdaemon'
    PIDDIR = '/var/run/hen'
    LOGDIR = '/var/log/hen/switchdaemon'
    LOGFILE = 'switchdaemon.log'
    PIDFILE = 'switchdaemon.pid'
    DBDIR = '%s/switchdb' % WORKDIR    
    GID = 18122 # hen
    UID = 18122 # root
    switchd = SwitchDaemon(False)
    switchd.setWorkingDir(WORKDIR)
    switchd.setDBDirectory(DBDIR)
    switchd.setPIDDir(PIDDIR)
    switchd.setLogDir(LOGDIR)
    switchd.setLogFile(LOGFILE)
    switchd.setPidFile(PIDFILE)
    switchd.setUid(UID)
    switchd.setGid(GID)
    switchd.start()

if __name__ == "__main__":
    main()
