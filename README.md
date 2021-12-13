# Roomba-polyglot
This is the Roomba Node Server for the ISY Polyglot V3 interface.  
(c) fahrer16 aka Brian Feeney.  
(c) Bob Paauwe.
MIT license. 

This project functions with Roomba WiFi enabled vacuums running version 2 firmware.  Currently, Roomba 980, Roomba 960, Roomba 890, and Roomba 690.

Roomba vacuums have a local interface reverse-engineered in the following projects.  Without the efforts of those developers, this project would not have been possible.
 * https://github.com/koalazak/dorita980
 * https://github.com/NickWaterton/Roomba980-Python

Use of a satic IP address for each Roomba is recommend.  If the Roomba IP address changes, you will need to re-discover if at the new IP address for the node server to continue working.  Either set a static IP through Roomba app or through router.

The Roomba980-Python Github linked above explains the limitations of connections to Roomba vacuums.  This node server is configured to keep a constant local connection to each vacuum.  Only one location connection is possible but it is still possible to use the app with a cloud connection to the vacuum.  I recommend preventing the Roomba's from reaching the internet though, so that they don't update their firmware automatically to a version not compatible with this node server.
 
# Installation Instructions:
1. Go to the Polyglot store and click "Install" for the Roomba node server.

The node server will then start the discovery process and for each Roomba found, it will prompt via a notice for you to press and hold the "Home" button on the vacuum to allow the node server to query the password.

Once the vacuums have been discovered, the node server will create nodes for each vacuum found and you will be able to use them within the ISY.

# Re-discovery:
Should the initial discovery process fail, or if something changes with your Roombas (add new devices, decommission devices, IP address change), you can run the disovery process manually using the "Discover" button from the Polyglot Node Server Details dashboard.
  
## Version History:
1.0.0: Initial Release
1.1.0: Only update WiFi strength in ISY if the reported value has changed by more than 15% since the last update
1.1.1: Corrected display name of parameter 'GV7' from 'Bin Present' to 'Bin Full'
1.1.2: Updated requirements file to use forked repository of Roomba980 project.
1.1.3: Update to account for changes to json reported from i7 series Roombas.
1.1.4: Updated underlying Roomba980 python project with changes that have been made in base repo.
2.0.0: Port to run on Polyglot version 3

## Known Issues:
1. Commands that allow for a parameter value to be passed don't seem to be present in admin console unless the profile is uploaded twice.  May be an issue with ISY994i (This was developed using version 5.0.10E).
2. Base Roomba980-Python project allows for a dynamic map to be drawn.  This node server does not yet implement that functionality.
3. Roomba values are currently updated every 5 seconds (unless shortPoll duration is changed).  There could be a bit of a lag when issuing command or changing parameter values before they're updated in the ISY.
