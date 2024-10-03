from ncclient import manager
from ncclient.xml_ import to_ele
import time
import xml.etree.ElementTree as ET
from xml.dom.minidom import parseString, Document

class NetconfRUClient:
    def __init__(self, host, port, username, password, response_file="netconf_responses.xml", capabilities_file='netconf_capabilty.xml'):
        """
        Initialize the connection details for the RU and specify the file for saving responses.
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.session = None
        self.response_file = response_file
        self.capabilities_file = capabilities_file

    def connect(self):
        """
        Establish an SSH NETCONF connection to the RU.
        """
        try:
            self.session = manager.connect(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                hostkey_verify=False
            )
            print(f"Successfully connected to RU at {self.host}")
        except Exception as e:
            print(f"Failed to connect to RU: {str(e)}")
            self.session = None

    def save_to_file(self, xml_data, message=""):
        """
        Pretty print the XML response and save it to a file.
        """
        # Parse and format the XML string
        try:
            dom = parseString(xml_data)
            pretty_xml = dom.toprettyxml(indent="  ")

            # Write to the file
            with open(self.response_file, 'a') as file:
                if message:
                    file.write(f"\n<!-- {message} -->\n")
                file.write(pretty_xml)
                file.write("\n")
            print(f"Response saved to {self.response_file}")
        except Exception as e:
            print(f"Failed to save XML response: {str(e)}")

    def save_capabilities(self):
        """
        Retrieve and save the NETCONF capabilities supported by the RU in a separate XML file.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return

        # Create an XML document for capabilities
        doc = Document()
        root = doc.createElement("capabilities")
        doc.appendChild(root)

        # Loop through the capabilities and add them to the document
        for capability in self.session.server_capabilities:
            capability_element = doc.createElement("capability")
            capability_text = doc.createTextNode(capability)
            capability_element.appendChild(capability_text)
            root.appendChild(capability_element)

        # Save the document to the capabilities file
        with open(self.capabilities_file, 'w') as file:
            file.write(doc.toprettyxml(indent="  "))

        print(f"Capabilities saved to {self.capabilities_file}")

    def check_supervision_status(self):
        """
        Retrieve the current supervision status of the O-RU.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return None

        # Corrected XPath to retrieve supervision status
        filter_payload = """
        <filter xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
          <supervision-status xmlns="urn:o-ran:supervision:1.0"/>
        </filter>
        """
        try:
            response = self.session.get(filter=filter_payload)
            xml_str = response.xml

            # Save the retrieved status to the file for logging
            self.save_to_file(response.xml, message="Supervision Status Retrieval")

            # Check if supervision status is present in the response
            if "<supervision-status>unsupervised</supervision-status>" in xml_str:
                print("Current supervision status: UNSUPERVISED")
                return "unsupervised"
            elif "<supervision-status>supervised</supervision-status>" in xml_str:
                print("Current supervision status: SUPERVISED")
                return "supervised"
            else:
                print("Supervision status not found in the response.")
                return "unsupervised"
        except Exception as e:
            print(f"Failed to retrieve supervision status: {str(e)}")
            return None




    def subscribe_to_netconf_notifications(self):
        """
        Subscribe to the /o-ran-supervision:supervision-notification stream to enter supervised mode.
        """
        try:
            # XML for subscribing to the /o-ran-supervision:supervision-notification stream
            subscription_rpc = """
            <rpc xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="101">
                <create-subscription xmlns="urn:ietf:params:xml:ns:netmod:notification">
                    <stream>NETCONF</stream>
                </create-subscription>
            </rpc>
            """
            
            # Convert XML to an Element and send the request
            rpc_element = to_ele(subscription_rpc)
            response = self.session.dispatch(rpc_element)
            
            print("Subscribed to the supervision notification stream successfully.")
             # Save the response to the file
            self.save_to_file(response.xml, message="Supervision Mode entered")
            # print(response.xml)  # Print the response for verification
            return response
        except Exception as e:
            print(f"Failed to subscribe: {e}")
            return None
        
    def reset_supervision_watchdog(self):
        """
        Reset the supervision watchdog timer using the supervision-watchdog-reset RPC with the provided parameters.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return

        # Build the correct XML structure using ElementTree
        rpc = ET.Element("rpc", {
            "xmlns": "urn:ietf:params:xml:ns:netconf:base:1.0",
            "message-id": "1"
        })

        # Create the supervision-watchdog-reset element
        supervision_reset = ET.SubElement(rpc, "supervision-watchdog-reset", {
            "xmlns": "urn:o-ran:supervision:1.0"
        })

        # Add sub-elements for notification interval and guard timer
        notification_interval = ET.SubElement(supervision_reset, "supervision-notification-interval")
        notification_interval.text = "60000"

        guard_timer_overhead = ET.SubElement(supervision_reset, "guard-timer-overhead")
        guard_timer_overhead.text = "5"

        # Convert the ElementTree structure to a string
        watchdog_reset_rpc = ET.tostring(rpc, encoding="utf-8", method="xml").decode('utf-8')

        try:
            # Convert the XML string to an Element using ncclient's to_ele
            rpc_element = to_ele(watchdog_reset_rpc)

            # Dispatch the RPC request
            response = self.session.dispatch(rpc_element)
            print("Supervision watchdog reset successfully.")

            # Save the response to the file
            self.save_to_file(response.xml, message="Supervision Watchdog Reset")
            return response

        except Exception as e:
            print(f"Failed to reset supervision watchdog: {str(e)}")
            return None
        
    def get_available_streams(self):
        """
        Use the 'get' operation to retrieve available notification streams.
        """
        filter_xml = """
        <netconf xmlns="urn:ietf:params:xml:ns:netmod:notification">
            <streams/>
        </netconf>
        """
        try:
            response = self.session.get(filter=to_ele(filter_xml))
            # print("Available Notification Streams:")
            self.save_to_file(response.xml, message="Available Notification Streams")  # This prints the XML response, which will list available streams
        except Exception as e:
            print(f"Error retrieving notification streams: {str(e)}")
    def receive_notifications(self):
        """
        Wait for notifications from the O-RU once the subscription is created.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return

        print("Waiting for notifications...")
        try:
            for notification in self.session.take_notification(timeout=10):
                # Handle the received notification
                print(f"Received Notification: {notification.notification_xml}")
                self.save_to_file(notification.notification_xml, message="Supervision Notification Received")
        except Exception as e:
            print(f"Failed to receive notifications: {str(e)}")

    def configure_call_home(self, ipv4_address, port, interface_name="MPLANE-INTERFACE", sub_interface="10"):
        """
        Configure the Call Home connection using the specified client IPv4 address, port, interface name, and sub-interface.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return

        # Updated XML payload for Call Home based on the provided sample output structure
        config_payload = f"""
        <config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
        <mplane-info xmlns="urn:o-ran:mplane-interfaces:1.0">
            <m-plane-interfaces>
            <m-plane-sub-interfaces>
                <interface-name>{interface_name}</interface-name>
                <sub-interface>{sub_interface}</sub-interface>
                <client-info>
                <mplane-ipv4-info>
                    <mplane-ipv4>{ipv4_address}</mplane-ipv4>
                    <port>{port}</port>
                </mplane-ipv4-info>
                </client-info>
            </m-plane-sub-interfaces>
            </m-plane-interfaces>
        </mplane-info>
        </config>
        """

        try:
            response = self.session.edit_config(target='running', config=config_payload)
            print(f"Call Home configuration applied for {ipv4_address}:{port}")
            
            # Save the response to the file
            self.save_to_file(response.xml, message="Call Home Configuration Response")
            return response
        except Exception as e:
            print(f"Failed to configure Call Home: {str(e)}")
            return None
        
    def retrieve_tx_array_carrier_info(self):
        """
        Retrieve the TX array carriers using the correct XPath and save the information to the XML file.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return None

        # XPath to retrieve TX array carriers
        filter_payload = """
        <filter xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
          <user-plane-configuration xmlns="urn:o-ran:uplane-conf:1.0">
            <tx-array-carriers/>
          </user-plane-configuration>
        </filter>
        """
        try:
            response = self.session.get(filter=filter_payload)
            xml_str = response.xml

            # Save the TX array carrier information
            self.save_to_file(response.xml, message="TX Array Carrier Information")
            return xml_str
        except Exception as e:
            print(f"Failed to retrieve TX array carrier information: {str(e)}")
            return None

    def retrieve_rx_array_carrier_info(self):
        """
        Retrieve the RX array carriers using the correct XPath and save the information to the XML file.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return None

        # XPath to retrieve RX array carriers
        filter_payload = """
        <filter xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
          <user-plane-configuration xmlns="urn:o-ran:uplane-conf:1.0">
            <rx-array-carriers/>
          </user-plane-configuration>
        </filter>
        """
        try:
            response = self.session.get(filter=filter_payload)
            xml_str = response.xml

            # Save the RX array carrier information
            self.save_to_file(response.xml, message="RX Array Carrier Information")
            return xml_str
        except Exception as e:
            print(f"Failed to retrieve RX array carrier information: {str(e)}")
            return None

    def configure_tx_array_carrier(self, name, center_of_channel_bandwidth, absolute_frequency_center, channel_bandwidth, gain):
        """
        Configure a TX array carrier on the RU using the edit-config RPC if it does not already exist.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return

        # Check if the TX array carrier already exists
        tx_info = self.retrieve_tx_array_carrier_info()
        if f"<name>{name}</name>" in tx_info:
            print(f"TX Array Carrier '{name}' already exists, skipping configuration.")
            return

        # XML payload for creating TX array carrier
        config_payload = f"""
        <config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
          <user-plane-configuration xmlns="urn:o-ran:uplane-conf:1.0">
            <tx-array-carriers>
              <name>{name}</name>
              <center-of-channel-bandwidth>{center_of_channel_bandwidth}</center-of-channel-bandwidth>
              <absolute-frequency-center>{absolute_frequency_center}</absolute-frequency-center>
              <channel-bandwidth>{channel_bandwidth}</channel-bandwidth>
              <type>NR</type>
              <gain>{gain}</gain>
              <downlink-radio-frame-offset>0</downlink-radio-frame-offset>
              <downlink-sfn-offset>0</downlink-sfn-offset>
            </tx-array-carriers>
          </user-plane-configuration>
        </config>
        """

        try:
            response = self.session.edit_config(target='running', config=config_payload)
            print(f"TX Array Carrier '{name}' configured successfully.")
            
            # Save the response to the file
            self.save_to_file(response.xml, message="TX Array Carrier Configuration")
            return response
        except Exception as e:
            print(f"Failed to configure TX array carrier: {str(e)}")
            return None

    def configure_rx_array_carrier(self, name, center_of_channel_bandwidth, absolute_frequency_center, channel_bandwidth, gain_correction, n_ta_offset):
        """
        Configure an RX array carrier on the RU using the edit-config RPC if it does not already exist.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return

        # Check if the RX array carrier already exists
        rx_info = self.retrieve_rx_array_carrier_info()
        if f"<name>{name}</name>" in rx_info:
            print(f"RX Array Carrier '{name}' already exists, skipping configuration.")
            return

        # XML payload for creating RX array carrier
        config_payload = f"""
        <config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
          <user-plane-configuration xmlns="urn:o-ran:uplane-conf:1.0">
            <rx-array-carriers>
              <name>{name}</name>
              <center-of-channel-bandwidth>{center_of_channel_bandwidth}</center-of-channel-bandwidth>
              <absolute-frequency-center>{absolute_frequency_center}</absolute-frequency-center>
              <channel-bandwidth>{channel_bandwidth}</channel-bandwidth>
              <type>NR</type>
              <downlink-radio-frame-offset>0</downlink-radio-frame-offset>
              <downlink-sfn-offset>0</downlink-sfn-offset>
              <gain-correction>{gain_correction}</gain-correction>
              <n-ta-offset>{n_ta_offset}</n-ta-offset>
            </rx-array-carriers>
          </user-plane-configuration>
        </config>
        """

        try:
            response = self.session.edit_config(target='running', config=config_payload)
            print(f"RX Array Carrier '{name}' configured successfully.")
            
            # Save the response to the file
            self.save_to_file(response.xml, message="RX Array Carrier Configuration")
            return response
        except Exception as e:
            print(f"Failed to configure RX array carrier: {str(e)}")
            return None
        
    def delete_tx_array_carrier(self, name, center_of_channel_bandwidth, absolute_frequency_center, channel_bandwidth, gain):
        """
        Delete a TX array carrier from the RU using the edit-config RPC.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return

        # XML payload for deleting TX array carrier
        config_payload = f"""
        <config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
          <user-plane-configuration xmlns="urn:o-ran:uplane-conf:1.0">
            <tx-array-carriers nc:operation="delete"
              xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
              <name>{name}</name>
              <center-of-channel-bandwidth>{center_of_channel_bandwidth}</center-of-channel-bandwidth>
              <absolute-frequency-center>{absolute_frequency_center}</absolute-frequency-center>
              <channel-bandwidth>{channel_bandwidth}</channel-bandwidth>
              <type>NR</type>
              <gain>{gain}</gain>
              <downlink-radio-frame-offset>0</downlink-radio-frame-offset>
              <downlink-sfn-offset>0</downlink-sfn-offset>
            </tx-array-carriers>
          </user-plane-configuration>
        </config>
        """

        try:
            response = self.session.edit_config(target='running', config=config_payload)
            print(f"TX Array Carrier '{name}' deleted successfully.")
            
            # Save the response to the file
            self.save_to_file(response.xml, message="TX Array Carrier Deletion")
            return response
        except Exception as e:
            print(f"Failed to delete TX array carrier: {str(e)}")
            return None

    def delete_rx_array_carrier(self, name, center_of_channel_bandwidth, absolute_frequency_center, channel_bandwidth, gain_correction, n_ta_offset):
        """
        Delete an RX array carrier from the RU using the edit-config RPC.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return

        # XML payload for deleting RX array carrier
        config_payload = f"""
        <config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
          <user-plane-configuration xmlns="urn:o-ran:uplane-conf:1.0">
            <rx-array-carriers nc:operation="delete"
              xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
              <name>{name}</name>
              <center-of-channel-bandwidth>{center_of_channel_bandwidth}</center-of-channel-bandwidth>
              <absolute-frequency-center>{absolute_frequency_center}</absolute-frequency-center>
              <channel-bandwidth>{channel_bandwidth}</channel-bandwidth>
              <type>NR</type>
              <downlink-radio-frame-offset>0</downlink-radio-frame-offset>
              <downlink-sfn-offset>0</downlink-sfn-offset>
              <gain-correction>{gain_correction}</gain-correction>
              <n-ta-offset>{n_ta_offset}</n-ta-offset>
              <active>INACTIVE</active>
            </rx-array-carriers>
          </user-plane-configuration>
        </config>
        """

        try:
            response = self.session.edit_config(target='running', config=config_payload)
            print(f"RX Array Carrier '{name}' deleted successfully.")
            
            # Save the response to the file
            self.save_to_file(response.xml, message="RX Array Carrier Deletion")
            return response
        except Exception as e:
            print(f"Failed to delete RX array carrier: {str(e)}")
            return None

    def get_running_config(self):
        """
        Retrieve the running configuration of the RU.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return
        
        try:
            response = self.session.get_config(source='running')
            print("Running configuration retrieved successfully.")
            
            # Save the running configuration to the file
            self.save_to_file(response.xml, message="Running Configuration")
            return response.xml
        except Exception as e:
            print(f"Failed to retrieve running configuration: {str(e)}")
            return None
        
    def retrieve_carrier_status(self, tx_name, rx_name):
        """
        Retrieve the current status (ACTIVE or INACTIVE) of both TX and RX array carriers.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return None, None

        # XPath to retrieve the active status of TX and RX array carriers
        filter_payload = f"""
        <filter xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
          <user-plane-configuration xmlns="urn:o-ran:uplane-conf:1.0">
            <tx-array-carriers>
              <name>{tx_name}</name>
              <active/>
            </tx-array-carriers>
            <rx-array-carriers>
              <name>{rx_name}</name>
              <active/>
            </rx-array-carriers>
          </user-plane-configuration>
        </filter>
        """
        try:
            response = self.session.get(filter=filter_payload)
            xml_str = response.xml

            # Save the retrieved status to the file for logging
            self.save_to_file(response.xml, message="Carrier Status Retrieval")

            # Parse the active status of both TX and RX carriers
            tx_active = "INACTIVE"
            rx_active = "INACTIVE"
            if f"<name>{tx_name}</name>" in xml_str and "<active>ACTIVE</active>" in xml_str:
                tx_active = "ACTIVE"
            if f"<name>{rx_name}</name>" in xml_str and "<active>ACTIVE</active>" in xml_str:
                rx_active = "ACTIVE"

            print(f"Current status - TX: {tx_active}, RX: {rx_active}")
            return tx_active, rx_active
        except Exception as e:
            print(f"Failed to retrieve carrier status: {str(e)}")
            return None, None

    def activate_carriers(self, tx_name, rx_name):
        """
        Activate both TX and RX array carriers if they are currently inactive.
        The TX array carrier cannot be activated without the RX array carrier being activated in the same RPC message.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return

        # Retrieve the current status of TX and RX carriers
        tx_status, rx_status = self.retrieve_carrier_status(tx_name, rx_name)

        if tx_status == "ACTIVE" and rx_status == "ACTIVE":
            print(f"Both TX ({tx_name}) and RX ({rx_name}) array carriers are already ACTIVE.")
            return

        # XML payload to activate both TX and RX array carriers if they are inactive
        config_payload = f"""
        <config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
          <user-plane-configuration xmlns="urn:o-ran:uplane-conf:1.0">
            <tx-array-carriers>
              <name>{tx_name}</name>
              <active>ACTIVE</active>
            </tx-array-carriers>
            <rx-array-carriers>
              <name>{rx_name}</name>
              <active>ACTIVE</active>
            </rx-array-carriers>
          </user-plane-configuration>
        </config>
        """

        try:
            response = self.session.edit_config(target='running', config=config_payload)
            print(f"TX Array Carrier '{tx_name}' and RX Array Carrier '{rx_name}' activated successfully.")
            
            # Save the response to the file
            self.save_to_file(response.xml, message="Carriers Activation")
            return response
        except Exception as e:
            print(f"Failed to activate carriers: {str(e)}")
            return None

    def deactivate_carriers(self, tx_name, rx_name):
        """
        Deactivate both TX and RX array carriers only if they are currently active.
        The TX array carrier cannot be deactivated without the RX array carrier being deactivated in the same RPC message.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return

        # Retrieve the current status of TX and RX carriers
        tx_status, rx_status = self.retrieve_carrier_status(tx_name, rx_name)

        if tx_status == "INACTIVE" and rx_status == "INACTIVE":
            print(f"Both TX ({tx_name}) and RX ({rx_name}) array carriers are already INACTIVE.")
            return

        # XML payload to deactivate both TX and RX array carriers if they are active
        config_payload = f"""
        <config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
          <user-plane-configuration xmlns="urn:o-ran:uplane-conf:1.0">
            <tx-array-carriers>
              <name>{tx_name}</name>
              <active>INACTIVE</active>
            </tx-array-carriers>
            <rx-array-carriers>
              <name>{rx_name}</name>
              <active>INACTIVE</active>
            </rx-array-carriers>
          </user-plane-configuration>
        </config>
        """

        try:
            response = self.session.edit_config(target='running', config=config_payload)
            print(f"TX Array Carrier '{tx_name}' and RX Array Carrier '{rx_name}' deactivated successfully.")
            
            # Save the response to the file
            self.save_to_file(response.xml, message="Carriers Deactivation")
            return response
        except Exception as e:
            print(f"Failed to deactivate carriers: {str(e)}")
            return None
        

    def retrieve_ru_states(self):
        """
        Retrieve the RU states (admin, power, oper, availability, usage) defined in ietf-hardware and o-ran-hardware YANG modules.
        """
        if not self.session:
            print("No active session to the RU. Please connect first.")
            return
        
        # XPath to retrieve the RU states with the correct namespace
        filter_payload = """
        <filter xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
          <hardware xmlns="urn:ietf:params:xml:ns:yang:ietf-hardware">
            <component>
              <name>benetel_RU</name>
              <state/>
            </component>
          </hardware>
        </filter>
        """
        
        try:
            # Send the get RPC with the proper namespace for ietf-hardware
            response = self.session.get(filter=filter_payload)
            print("RU states retrieved successfully.")
            
            # Save the response to the file
            self.save_to_file(response.xml, message="RU States Response")
            return response.xml
        except Exception as e:
            print(f"Failed to retrieve RU states: {str(e)}")
            return None
        
    def get_all_state_data(self):
        """
        Perform a generic 'get' operation to retrieve state data and look for the streams manually.
        """
        try:
            # Sending a generic <get> request without filter
            response = self.session.get()
            self.save_to_file(response.xml, message="All RU states")  # Print the full XML response
        except Exception as e:
            print(f"Error retrieving state data: {str(e)}")
        

    def close_connection(self):
        """
        Close the NETCONF session to the RU.
        """
        if self.session:
            self.session.close_session()
            print("NETCONF session closed.")
        else:
            print("No active session to close.")


if __name__ == "__main__":
    # Initialize the RU client with connection details and specify a file to save XML responses
    ru_client = NetconfRUClient(
        host='10.1.8.14',     # RU IP address
        port=830,             # NETCONF SSH port
        username='oranbenetel',  # Username for RU
        password='aaBB00!$aaBB00!$',  # Password for RU
        response_file="netconf_responses.xml"  # Output file for saving responses
    )

    # Step 1: Connect to the RU
    ru_client.connect()

    # ru_client.reset_supervision_watchdog()

    # # supervision_status = ru_client.check_supervision_status()
    # ru_client.get_notification_streams()
    ru_client.subscribe_to_netconf_notifications()
    # ru_client.configure_call_home('10.1.8.14',830)

    # Step 3: If in unsupervised mode, subscribe to the supervision-notification stream
    # if supervision_status == "unsupervised":
    #     subscription_response = ru_client.subscribe_to_netconf_notifications()
    #     if subscription_response:
    #         try:
    #         # Reset the supervision watchdog periodically in a background loop
    #             ru_client.periodically_reset_watchdog(interval=60, overhead=10)
    #             # Step 4: Wait and receive notifications
    #             ru_client.receive_notifications()
    #         except KeyboardInterrupt:
    #             print("Stopping the watchdog reset process.")
            

    # activation_response = ru_client.activate_carriers(
    #     tx_name="TxArrayCarrier0",
    #     rx_name="RxArrayCarrier0"
    # )

    # ru_client.get_available_streams()

    # Step 3: Deactivate both TX and RX Array Carriers
    # deactivation_response = ru_client.deactivate_carriers(
    #     tx_name="TxArrayCarrier0",
    #     rx_name="RxArrayCarrier0"
    # )

    # Step 2: Configure Call Home with a specific client IP and port
    # call_home_response = ru_client.configure_call_home(ipv4_address="MPLANE-INTERFACE", port=80)

    # # Optionally print the response from the RU after configuration
    # if call_home_response:
    #     print("Call Home configuration response:", call_home_response)

    # Step 3: Retrieve and print the running configuration
    # running_config = ru_client.get_running_config()
    # if running_config:
    #     print("Running configuration retrieved.")

    # # Step 4: Retrieve and save the RU states (admin, power, oper, availability, usage)
    # ru_states = ru_client.retrieve_ru_states()
    # if ru_states:
    #     print("RU states retrieved.")

    # tx_carrier_response = ru_client.configure_tx_array_carrier(
    #     name="TxArrayCarrier0",
    #     center_of_channel_bandwidth=4150000000,
    #     absolute_frequency_center=653616,
    #     channel_bandwidth=100000000,
    #     gain=0.0
    # )

    # if tx_carrier_response:
    #     print("TX Array Carrier configuration response:", tx_carrier_response)

    # rx_carrier_response = ru_client.configure_rx_array_carrier(
    #     name="RxArrayCarrier0",
    #     center_of_channel_bandwidth=4150000000,
    #     absolute_frequency_center=653616,
    #     channel_bandwidth=100000000,
    #     gain_correction=0.0,
    #     n_ta_offset=25600
    # )

    # if rx_carrier_response:
    #     print("RX Array Carrier configuration response:", rx_carrier_response)

    # ru_carrier_response = ru_client.retrieve_tx_array_carrier_info()
    # if ru_carrier_response:
    #     print("TX Array Carrier retrievel response:", ru_carrier_response)

    # ru_rx_carrier_response = ru_client.retrieve_tx_array_carrier_info()
    # if ru_rx_carrier_response:
    #     print("TX Array Carrier retrievel response:", ru_rx_carrier_response)

     # Step 2: Delete the TX Array Carrier
    # tx_carrier_deletion_response = ru_client.delete_tx_array_carrier(
    #     name="TxArrayCarrier0",
    #     center_of_channel_bandwidth=4150000000,
    #     absolute_frequency_center=653616,
    #     channel_bandwidth=100000000,
    #     gain=0.0
    # )

    # if tx_carrier_deletion_response:
    #     print("TX Array Carrier configuration response:", tx_carrier_deletion_response)

    # # Step 3: Delete the RX Array Carrier
    # rx_carrier_deletion_response = ru_client.delete_rx_array_carrier(
    #     name="RxArrayCarrier0",
    #     center_of_channel_bandwidth=4150000000,
    #     absolute_frequency_center=653616,
    #     channel_bandwidth=100000000,
    #     gain_correction=0.0,
    #     n_ta_offset=25600
    # )

    # if rx_carrier_deletion_response:
    #     print("TX Array Carrier configuration response:", rx_carrier_deletion_response)

    # Step 5: Close the NETCONF session
    ru_client.close_connection()
