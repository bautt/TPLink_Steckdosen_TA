# TPLink_Steckdosen_TA
TPLink_Steckdosen_TA for Splunk (HS110 und KP115)
This app runs a python script to collect energy meter data from TP Link smart wlan plugs with energy meters and puts this data in to the metric index in Splunk. The app contains a modular input to configure data collection and a simple example dashboard based on the metrics. <p>
It is developed from this script: https://github.com/softScheck/tplink-smartplug/blob/master/tplink_smartplug.py and uses some props/transforms to put it to the Splunk metric index and a Splunk Modular input to configure and run it. 

## Usage

![Configuration](configure.png)



## Support

This app is not officially supported by Splunk and is provided as is.

## License

[Apache License 2.0](LICENSE.md)
