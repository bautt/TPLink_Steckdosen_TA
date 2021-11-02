import argparse
import socket
import json 
import datetime
from struct import pack

import sys, time, os
import threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

path_to_mod_input_lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modular_input.zip')
sys.path.insert(0, path_to_mod_input_lib)
from modular_input import Field, ModularInput, URLField, DurationField, IntegerField, BooleanField, RangeField
from modular_input.shortcuts import forgive_splunkd_outages
from modular_input.secure_password import get_secure_password
from modular_input.server_info import ServerInfo
from splunk.models.field import Field as ModelField
from splunk.models.field import IntField as ModelIntField
import splunk

import xml.dom.minidom, xml.sax.saxutils
import logging
import tarfile, gzip


class TPLinkSteckdosenTA(ModularInput):
    DEFAULT_THREAD_LIMIT = 1

    def __init__(self, timeout=30, thread_limit=None):

        scheme_args = {'title': "TP Link Steckdosen TA",
                       'description': "Connects to TP Link smart energy meter plugs in a fashionable manner.",
                       'use_external_validation': "true",
                       'streaming_mode': "xml",
                       'use_single_instance': "true"}

        args = [
                Field("name", "Name", "Typically just a name for your smart plug aka Steckdose", empty_allowed=False),
                Field("hostname", "Hostname", "Resolvable hostname or IP", empty_allowed=False),
                Field("tpsport", "Port", "Steckdose's specific port (Default: 9999)", none_allowed=True, empty_allowed=False),
                Field("tpsmindex", "Metric Index", "Override index setting for metrix", none_allowed=True, empty_allowed=False),
                Field("tpscommand", "Command", "Steckdose's special command to send (Default: energy)",none_allowed=True, empty_allowed=False),
                Field("timeout", "Timeout", "Steckdose's request timeout (Default: 10)",none_allowed=True, empty_allowed=False),
                Field("tpsinterval", "Interval", "Interval for this input in min (Default: 30s)",none_allowed=True, empty_allowed=False)]

        ModularInput.__init__(self, scheme_args, args, logger_name='tplinksteckdosenta_modular_input', logger_level=logging.INFO)

        if timeout > 0:
            self.timeout = timeout
        else:
            self.timeout = 30

        #if thread_limit is None:
        #    self.thread_limit = TPLinkSteckdosenTA.DEFAULT_THREAD_LIMIT
        #else:
        self.thread_limit = 1

        self.threads = {}
    
    def cleanup_threads(self, threads):
        # Keep track of the number of removed threads so that we can make sure to emit a log
        # message noting the number of threads
        removed_threads = 0

        # Clean up old threads
        for thread_stanza in list(threads):

            # If the thread isn't alive, prune it
            if not threads[thread_stanza].isAlive():
                removed_threads = removed_threads + 1
                self.logger.debug("Removing inactive thread for stanza=%s, thread_count=%i", thread_stanza, len(threads))
                del threads[thread_stanza]

        # If we removed threads, note the updated count in the logs so that it can be tracked
        if removed_threads > 0:
            self.logger.info("Removed inactive threads, thread_count=%i, removed_thread_count=%i", len(threads), removed_threads)

        return removed_threads

    def save_checkpoint(self, checkpoint_dir, stanza, last_run):
        """
        Save the checkpoint state.

        Arguments:
        checkpoint_dir -- The directory where checkpoints ought to be saved
        stanza -- The stanza of the input being used
        last_run -- The time when the analysis was last performed
        """

        self.save_checkpoint_data(checkpoint_dir, stanza, {'last_run' : last_run})

    def output_result(self, data, stanza, title, index=None, source=None, sourcetype=None,
                      host=None,unbroken=True, close=True, out=sys.stdout):
        """
        Create a string representing the event.

        Argument:
        result -- A result instance from a call to WebPing.ping
        stanza -- The stanza used for the input
        sourcetype -- The sourcetype
        source -- The source field value
        index -- The index to send the event to
        unbroken --
        close --
        out -- The stream to send the event to (defaults to standard output)
        """
        
        # Make the event
        event_dict = {'stanza': stanza, 'data' : data}

        if index is not None:
            event_dict['index'] = index

        if sourcetype is not None:
            event_dict['sourcetype'] = sourcetype

        if source is not None:
            event_dict['source'] = source

        if host is not None:
            event_dict['host'] = host

        event = self._create_event(self.document,params=event_dict, stanza=stanza, unbroken=unbroken, close=close)
        out.write(self._print_event(self.document, event))
        out.flush()
        
    def run(self, stanza, cleaned_params, input_config):
        # Make the parameters
        val_name = cleaned_params.get("name", None)
        val_hostname = cleaned_params.get("hostname", None)
        val_port = cleaned_params.get("tpsport", "9999")
        if (val_port is None):
            val_port = 9999

        val_command = cleaned_params.get("tpscommand", "energy")
        val_timeout = cleaned_params.get("timeout", 10)
        interval = cleaned_params.get("tpsinterval", "30")
        if (interval is None):
            interval = 30
        else:
            interval = int(interval)
        
        host = cleaned_params.get("host", socket.gethostname())
        if (host == "$decideOnStartup"):
            host = val_hostname

        sourcetype = cleaned_params.get("sourcetype", "tplink_event")
        index = cleaned_params.get("index", "main")
        val_index = cleaned_params.get("tpsmindex", None)
        if (val_index is not None):
            index = val_index
            sourcetype = "tplink_metrics"

        # Clean up old threads
        self.cleanup_threads(self.threads)

        # Stop if we have a running thread
        if stanza in self.threads:
            self.logger.debug("No need to execute this stanza since a thread already running for stanza=%s", stanza)

        # Determines if the input needs another run
        elif self.needs_another_run(input_config.checkpoint_dir, stanza, interval):
            def run_run():
                self.logger.info("Started run for stanza=%s", stanza)
                with self.lock:
                    version = 0.4
                    # Predefined Smart Plug Commands
                    # For a full list of commands, consult tplink_commands.txt
                    commands = {'info'     : '{"system":{"get_sysinfo":{}}}',
                                'on'       : '{"system":{"set_relay_state":{"state":1}}}',
                                'off'      : '{"system":{"set_relay_state":{"state":0}}}',
                                'ledoff'   : '{"system":{"set_led_off":{"off":1}}}',
                                'ledon'    : '{"system":{"set_led_off":{"off":0}}}',
                                'cloudinfo': '{"cnCloud":{"get_info":{}}}',
                                'wlanscan' : '{"netif":{"get_scaninfo":{"refresh":0}}}',
                                'time'     : '{"time":{"get_time":{}}}',
                                'schedule' : '{"schedule":{"get_rules":{}}}',
                                'countdown': '{"count_down":{"get_rules":{}}}',
                                'antitheft': '{"anti_theft":{"get_rules":{}}}',
                                'reboot'   : '{"system":{"reboot":{"delay":1}}}',
                                'reset'    : '{"system":{"reset":{"delay":1}}}',
                                'energy'   : '{"emeter":{"get_realtime":{}}}'
                    }
                    # Encryption and Decryption of TP-Link Smart Home Protocol
                    # XOR Autokey Cipher with starting key = 171

                    def encrypt(string):
                        key = 171
                        result = pack(">I", len(string))
                        for i in string:
                            a = key ^ ord(i)
                            key = a
                            result += bytes([a])
                        return result

                    def decrypt(string):
                        key = 171
                        result = ""
                        for i in string:
                            a = key ^ i
                            key = i
                            result += chr(a)
                        return result


                    # Set target IP, port and command to send
                    ip = val_hostname
                    cmd = commands[val_command]

                    self.logger.info("Finished preparation for request {hostname}:{port} {command} {timeout}".format(hostname=ip,port=val_port,command=cmd,timeout=val_timeout))
               
                    # Send command and receive reply
                    try:
                        sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock_tcp.settimeout(int(val_timeout))
                        sock_tcp.connect((ip, int(val_port)))
                        sock_tcp.settimeout(None)
                        sock_tcp.send(encrypt(cmd))
                        data = sock_tcp.recv(2048)
                        sock_tcp.close()

                        decrypted = decrypt(data[4:])

                        timestamp = datetime.datetime.now(tz=datetime.timezone.utc).timestamp()
                        event = {
                        "timestamp": timestamp,
                        "device": ip,
                        "inputname": val_name.replace("tplinksteckdosenta://", "")
                        }
                        emeter_str=decrypted
                        emeter = json.loads(emeter_str)
                        resultobject = emeter.get('emeter').get('get_realtime')
                        event.update(resultobject)
                        self.logger.info("Request succeeded {hostname}:{port} {command} {timeout}".format(hostname=ip,port=val_port,command=cmd,timeout=val_timeout))
                        self.output_result(json.dumps(event), stanza, val_name, index=index, sourcetype=sourcetype, host=host) 
                    except:
                        self.logger.error("Request failed {hostname}:{port} {command} {timeout}".format(hostname=ip,port=val_port,command=cmd,timeout=val_timeout))

                    # Get the time that the input last ran
                    last_ran = self.last_ran(input_config.checkpoint_dir, stanza)
                    # Save the checkpoint so that we remember when we last ran the input
                    self.save_checkpoint(input_config.checkpoint_dir, stanza, self.get_non_deviated_last_run(last_ran, interval, stanza))

                

            # If this is not running in multi-threading mode, then run it now in the main thread
            if self.thread_limit <= 1:
                run_run()

            # If the number of threads is at or above the limit, then wait until the number of
            # threads comes down
            elif len(self.threads) >= self.thread_limit:
                self.logger.warn("Thread limit has been reached and thus this execution will be skipped for stanza=%s, thread_count=%i", stanza, len(self.threads))

            # Execute the input as a separate thread
            else:

                # Start a thread
                t = threading.Thread(name="{stanza}".format(stanza=stanza), target=run_run)
                self.threads[stanza] = t
                t.start()

                self.logger.info("Added thread to the queue for stanza=%s, thread_count=%i", stanza, len(self.threads))

if __name__ == '__main__':

    connectapp = None

    try:
        connectapp = TPLinkSteckdosenTA()
        connectapp.execute()
        sys.exit(0)
    except Exception as e:

        # This logs general exceptions that would have been unhandled otherwise (such as coding
        # errors)
        if connectapp is not None and connectapp.logger is not None:
            connectapp.logger.exception("Unhandled exception was caught, this may be due to a defect in the script")
        else:
            raise e