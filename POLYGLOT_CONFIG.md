### Roomba robots are auto discovered
If no robots are configured when starting, the node server will start the discovery process.
This will look for Roomba devices on the network. For each device found, you will then have
to manually put the Roomba in to a mode that allows the node server to query the authentication
information from the device.  You will be prompted via a notice when this is required.

The discovered Roomba deivces are then saved so that future starts can skip the discovery process.

If you need to re-discover devices, use the "Discover" button in the UI to start the discovery
process.  This will clear any exising devices and start from an empty list.
