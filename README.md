# TPLink_Steckdosen_TA
TPLink_Steckdosen_TA for Splunk (HS110 und KP115)
This app runs a python script to collect energy meter data from TP Link smart wlan plugs with energy meters and puts this data in to the metric index in Splunk. The app contains a modular input to configure data collection and a simple example dashboard based on the metrics. <p>
It is developed from this script: https://github.com/softScheck/tplink-smartplug/blob/master/tplink_smartplug.py and uses some props/transforms to put energy meter data in to the Splunk metric index and a Splunk Modular input to configure and run it. 

## Installation 
1. Download the latest release (recommended) or clone the repo 
2. Install it like any other app through Splunk UI or just copy the folder in to $SPLUNK_HOME/etc/apps and restart

## Usage
Once installed you can go to  "Settings" > "Data inputs" > "TP Link Steckdosen TA" and configure a modular input for each smart plug.
 
## Support

This app is not officially supported by Splunk and is provided as is.

## License

[Apache License 2.0](LICENSE.md)
