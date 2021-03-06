#!/usr/local/bin/python
##################################################################################################################
# inventory.py: 
#
##################################################################################################################
import sys, os, time
sys.path.append("/home/arkell/u0/fhuici/development/svn/hen_scripts/lib")
os.environ["PATH"] += ":/usr/local/bin:/usr/bin"
from henmanager import HenManager

###########################################################################################
#   Main execution
###########################################################################################            
outputFilename = "/home/arkell/u0/www/data/inventory.html"
while 1:
    try:
        print "Updating inventory information..."
        manager = HenManager()
        nodes = manager.getNodes("all")

        result = ""
        for nodeTypeDictionary in nodes.values():
            for node in nodeTypeDictionary.values():
                result += str(node) + "\n"

        print "writing to file..."
        if (os.path.exists(outputFilename)):
            os.remove(outputFilename)                            
        outputFile = open(outputFilename, "w")
        outputFile.write("Content-type: text/html\n\n<html><head><title></title></head><body>\n")
        outputFile.write(result)
        outputFile.write("</body></html>\n")
        outputFile.close()
        print "done writing to file, sleeping..."
        time.sleep(5)

    except (KeyboardInterrupt, SystemExit):
        os._exit(1)
