"""
Unit test for metrics generation
"""

from datetime import datetime

from ssl_expiry_monitor import (
    generate_cloudwatch_metrics_per_hostname,
    get_expiry_delta_for_hostnames,
)


def test_main():
    _HOSTS_TO_MONITOR = [
        "thereisnospoon.ews-network.net:443",
        "https://thereisnospoon.ews-network.net",
        "https://thereisnospoon.ews-network.net:443",
        "http://thereisnospoon.ews-network.net",
    ]
    _HOSTS_EXPIRY = get_expiry_delta_for_hostnames(_HOSTS_TO_MONITOR, datetime.utcnow())
    _METRICS = generate_cloudwatch_metrics_per_hostname(_HOSTS_EXPIRY)
