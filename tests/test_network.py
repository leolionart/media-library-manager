import unittest
from unittest.mock import patch

from media_library_manager.network import discover_arp_hosts, discover_bonjour_services, discover_lan_devices


class NetworkDiscoveryTests(unittest.TestCase):
    @patch("media_library_manager.network.run_command")
    def test_discover_bonjour_services_parses_smb_device(self, run_command_mock) -> None:
        run_command_mock.side_effect = [
            "Timestamp     A/R    Flags  if Domain               Service Type         Instance Name\n"
            "12:00:00.000  Add        2  15 local.               _smb._tcp.           SynologyNAS\n",
            "Lookup SynologyNAS._smb._tcp.local\nSynologyNAS._smb._tcp.local. can be reached at nas.local.:445 (interface 15)\n",
            "",
            "",
            "",
        ]
        services = discover_bonjour_services()
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0]["service_label"], "SMB")
        self.assertEqual(services[0]["connect_url"], "smb://nas.local")

    @patch("media_library_manager.network.run_command")
    def test_discover_arp_hosts_parses_neighbors(self, run_command_mock) -> None:
        run_command_mock.return_value = "? (192.168.1.20) at aa:bb:cc:dd:ee:ff on en0 ifscope [ethernet]\n"
        hosts = discover_arp_hosts()
        self.assertEqual(len(hosts), 1)
        self.assertEqual(hosts[0]["ip_address"], "192.168.1.20")
        self.assertEqual(hosts[0]["mac_address"], "aa:bb:cc:dd:ee:ff")

    @patch("media_library_manager.network.run_command")
    def test_discover_arp_hosts_falls_back_to_ip_neigh(self, run_command_mock) -> None:
        run_command_mock.side_effect = [
            "",
            "192.168.1.20 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n",
        ]
        hosts = discover_arp_hosts()
        self.assertEqual(len(hosts), 1)
        self.assertEqual(hosts[0]["ip_address"], "192.168.1.20")
        self.assertEqual(hosts[0]["interface"], "eth0")
        self.assertEqual(hosts[0]["mac_address"], "aa:bb:cc:dd:ee:ff")

    @patch("media_library_manager.network.discover_bonjour_services")
    @patch("media_library_manager.network.discover_arp_hosts")
    def test_discover_lan_devices_merges_services_and_hosts(self, arp_mock, bonjour_mock) -> None:
        bonjour_mock.return_value = [
            {
                "instance": "SynologyNAS",
                "service_type": "_smb._tcp",
                "service_label": "SMB",
                "domain": "local.",
                "target": "nas.local",
                "port": 445,
                "connect_url": "smb://nas.local",
                "device_key": "nas.local",
            }
        ]
        arp_mock.return_value = [
            {
                "device_key": "nas.local",
                "display_name": "nas.local",
                "hostname": "nas.local",
                "ip_address": "192.168.1.20",
                "mac_address": "aa:bb:cc:dd:ee:ff",
                "interface": "en0",
            }
        ]
        payload = discover_lan_devices()
        self.assertEqual(payload["summary"]["devices"], 1)
        self.assertEqual(payload["devices"][0]["services"][0]["service_label"], "SMB")
        self.assertIn("smb://nas.local", payload["devices"][0]["connect_urls"])

    @patch("media_library_manager.network.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_network_command_returns_empty_output(self, _run_mock) -> None:
        from media_library_manager.network import run_command

        self.assertEqual(run_command(["dns-sd", "-B", "_smb._tcp", "local."], timeout=1), "")
