# Name:		sessionstore-parse.py
# Author:	Richard ROSALION
# Date:		March, 2012
# Notes:	Tool to parse partial (or complete) JSON records
#               from Firefox sessionstore.js
# Revisions:
# 		1.0     15/03/2012  Initial Version


import re, csv, collections, sys, inspect, time
from progressbar import *

# Debugging and user feedback options
LOOPFEEDBACK = 10
DEBUGLEVEL = 1

# Which fields do we want to capture
FIELDS = ['lastUpdated','url','title','ID','referrer','scroll','subframe','Path']


"""
Converts an UNIX date-time integer into a string in an excel-friendly format
Time is seconds since 1/1/1970
"""
def intUnixMSToDateTime(intUnixDateTime):
    inLocal = time.localtime(intUnixDateTime/1000)
    return time.strftime("%d-%b-%Y %H:%M:%S",inLocal)


""" Open a file for reading/writing (with error checking) """
def openFile(fileName, openType, defaultFile=sys.stdout,newline='\n'):
        if (fileName == ""):
                fileObject = defaultFile
        else:
                try: fileObject = open(fileName, openType, newline=newline)
                except IOError:
                        print("Error in trying to open the file %s. Check that the file exists." % (fileName))
                        raise

        return fileObject

""" Print a debug message if the current DEBUGLEVEL is set, including the calling function """
def debugMessage(message, messageDebugLevel = 10):
        if DEBUGLEVEL >= messageDebugLevel:
                indent = "  " * len(inspect.stack())
                print("%s%s: %s" % (indent, whoParent(), message), file=sys.stderr)

""" Return the name of the current function """                
def whoAmI():
        return inspect.stack()[1][3]

""" Return the name of the parent function"""
def whoParent():
        return inspect.stack()[2][3]
    

class csvWriter:
    fields = []
    _outFile = None
    _outWriter = None
    
    def __init__(self, fields, outFile, mode='w'):
        # Setup CSV File
        self._fields = fields
        self._outFile = openFile(outFile,mode,newline='')
        self._outWriter = csv.writer(self._outFile)
        # Write Header
        if '+' not in mode:
            self._outWriter.writerow(self._fields)

        debugMessage("Setup CSV File '%s' with fields: %s'" % (outFile, fields), 1)

    def writerow(self, dictRow):
        # Convert dictionary to ordered list
        listRow = []
        for field in self._fields:
            # Add value if it exists in dictionary
            if field in dictRow.keys():
                debugMessage("Found value for '%s' = '%s'" % (field, dictRow[field]), 20)
                listRow.append(dictRow[field])
            # Otherwise, add a blank record
            else:
                debugMessage("No value found for '%s'. Printing blank field.", 20)
                listRow.append(None)

        # Write row to CSV
        debugMessage("Attempting to write: %s" % listRow, 15)
        self._outWriter.writerow(listRow)

    def close(self):
        self._outFile.close()
        
                
        
class textTree:
    openLevel = "["
    closeLevel = "]"
    ignoreBetween = "\""
    _currPos = 0
    _text = ""

    def __init__(self, text, currPos = -1, openLevel="[", closeLevel="]", ignoreBetween="\""):
        self._text = text
        self.openLevel = openLevel
        self.closeLevel = closeLevel
        self.ignoreBetween = ignoreBetween
        
        if currPos == -1 or currPos >= len(text):
            self._currPos = len(text)-1
        else:
            self._currPos = currPos

    def nextUpTreeReverse(self):

        # Navigate back down string tree, work out full tree path to current node
        treeLevel = 0

        # Start just before selected location
        debugMessage("Finding previous opening bracket from offset %d" % (self._currPos), 20)

        while self._currPos > 0:

                # If we find the next level, we're done
                if treeLevel < 0:
                        debugMessage("Found matching bracket")
                        break

                # Otherwise, take a look at the previous character
                self._currPos -= 1
                currChar = self._text[self._currPos]

                # If we come across an "ignoreBetween" character, skip back until
                # the matching character - this is to ignore quoted sections
                if currChar in self.ignoreBetween:
                        matchingQuote = self._text.rfind(currChar, 0, self._currPos)
                        self._currPos = matchingQuote - 1
                        continue

                # Otherwise, we only care about opening/closing brackets
                elif currChar in self.openLevel:
                    treeLevel -= 1
                elif currChar in self.closeLevel:
                    treeLevel += 1
        


def parseJsonEntry(jsonEntry):

    # Treat jsonEntry as CSV, to separate out each key/value pair
    lineRead = csv.reader([jsonEntry])
    for arrEntry in lineRead:

        # For each field, read fields as CSV with ":" separator
        fields = csv.reader(arrEntry, delimiter=":")

        # Write fields to dictionary
        UrlRecord = {}
        for field in fields:
            key = field[0].strip('\{\[\"')
            value = field[1].strip('\{\[\"')

            # Create record to hold entry
            if key in FIELDS:
                UrlRecord[key] = value
                debugMessage("\tADDED\t%s: %s" % (key, value), 15)
            else:
                debugMessage("\tIGNORED\t%s: %s" % (key, value), 15)

        # Return dictionary
        return UrlRecord



def findJsonEntries(jsonBlob, showFeedback=True, csvWriter=None):
    entryOffsets = []

    # Do we need to show progress bars?
    if showFeedback and DEBUGLEVEL == 0: needFeedback = True
    else: needFeedback = False

    ##########################################
    # RUN REGEX TO FIND ENTRIES
    ##########################################

    # Setup Progress Bar for Regex Search
    if needFeedback:
        widgets = ['Running Search: ', Percentage(), ' ', Bar(), ETA()]
        pbar = ProgressBar(widgets=widgets, maxval=len(jsonBlob)).start()

    # First, find all occurances of `{"url":`
    debugMessage("Finding URL Entries", 1)
    for result in re.finditer("\{\"url\"\:", jsonBlob):
        if needFeedback: pbar.update(result.start())
        entryOffsets.append(result.start())

    # See if there's a date/"lastupdate" (if so, it becomes the date for all entries found)
    lastUpdatePretext = "\"lastUpdate\":"
    for result in re.finditer(lastUpdatePretext + "[0-9]*}", jsonBlob):
        # Pull date/time value from string
        dateTimeStart = result.start()+len(lastUpdatePretext)
        dateTimeEnd = result.end()-1
        strUnixDateTime = jsonBlob[dateTimeStart:dateTimeEnd]
        # Convert to INT
        intUnixDateTime = int(strUnixDateTime)
        # and to printable string
        strLastUpdated = intUnixMSToDateTime(intUnixDateTime)

    ##########################################
    # PROCESS INDIVIDUAL ENTRIES
    ##########################################
    
    # Setup Progress Bar for Processing Entries
    debugMessage("Processing URL Entries", 1)
    if needFeedback:
        widgets = ['Processing URL Entries: ', Percentage(), ' ', Bar(), ETA()]
        pbar = ProgressBar(widgets=widgets, maxval=len(entryOffsets)).start()

    # Now, process each occurance
    for i in range(len(entryOffsets)):

        if needFeedback and not (i % LOOPFEEDBACK): pbar.update(i)

        debugMessage("%d/%d. Offset=%d" % (i+1, len(entryOffsets), entryOffsets[i]), 10)

        # Start where the current "hit" was found
        start = entryOffsets[i]
        # End where the next hit is found (or, at the end of the string)
        if len(entryOffsets)-1 == i:
            end = len(jsonBlob)
        else:
            end = entryOffsets[i+1]
        
        # Starting with the opening "{", look for the matching closing bracket
        treeLevel = 0
        for currPos in range(start+1, end):
            # If we've found the closing bracket for the current section, we're done.
            if treeLevel < 0:
                break
            # Otherwise, find the closing bracket!
            if jsonBlob[currPos] == '{':
                treeLevel += 1
            if jsonBlob[currPos] == '}':
                treeLevel -= 1

        end = currPos

        # Strip leading and closing characters
        # strJsonEntry should be a flat string something like:
        # "url":"http://ebay","title":"My eBay: Messages: Inbox","subframe":true,"ID":1471
        strJsonEntry = jsonBlob[start:end].strip("\{\}\[\]")
        debugMessage("Found JSON Entry: %s" % jsonBlob[start:end], 10)

        # Convert string jsonEntry to Dictionary
        jsonEntry = parseJsonEntry(strJsonEntry)

        # Navigate back down JSON string to work out path to current node
        treePath = ""
        tt = textTree(jsonBlob, currPos=start,openLevel="[",closeLevel="]")
        
        while tt._currPos > 0:
                
                # Find the previous opening bracket
                tt.nextUpTreeReverse()
                if tt._currPos == 0: break
                
                # Get the name of this node
                startNodeName = jsonBlob.rfind('"', 0, tt._currPos-len('":['))+1
                nodeName = jsonBlob[startNodeName:tt._currPos-len('":')]
                treePath = '%s/%s' % (nodeName, treePath)

        # Set additional fields
        jsonEntry['Path'] = treePath
        jsonEntry['lastUpdated'] = strLastUpdated

        # Print to CSV
        if csvWriter != None:
            csvWriter.writerow(jsonEntry)
       





if __name__ == '__main__':

    print(intUnixMSToDateTime(1289247439269))
    # Open input/output files
    debugMessage("Opening Required Files", 1)
    inFile = open('sessionstore.js', 'r')
    outWriter = csvWriter(FIELDS, 'sessionstore.js.csv')

    # Read all '{"url":' entries in input file
    debugMessage("Reading JSON Entries", 1)
    entries = findJsonEntries(inFile.read(), csvWriter=outWriter)

    # Cleanup
    inFile.close()
    outWriter.close()
    debugMessage("Done.", 1)

   

















