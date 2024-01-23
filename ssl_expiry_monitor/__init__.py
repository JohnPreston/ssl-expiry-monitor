# SPDX-License-Identifier: MIT
# Copyright 2021 John Mille<john@ews-network.net>

"""Main module."""

import re
import ssl
from datetime import datetime

import OpenSSL
from boto3.session import Session
from compose_x_common.aws import get_session
from compose_x_common.compose_x_common import chunked_iterable, set_else_none

__author__ = """John Preston"""
__email__ = "john@compose-x.io"
__version__ = "0.1.0"


HOSTNAME_RE = re.compile(
    r"(?P<scheme>[a-zA-Z://]+(?<=://))?(?P<hostname>[A-Za-z0-9.-]+)(?::(?P<port>\d+)$)?"
)
KNOWN_SCHEMES: dict = {"https://": 443, "http://": 80, "ftp://": 21}


def evaluate_hostname_cert_expiry(hostname: str, port: int) -> datetime:
    """Function to query a hostname and port and validate the SSL certificate expiry date"""
    try:
        cert = ssl.get_server_certificate((hostname, port))
        x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
        return datetime.strptime(x509.get_notAfter().decode(), "%Y%m%d%H%M%SZ")
    except Exception as error:
        print(error)
        return None


def get_expiry_delta_in_seconds(expiry_date: datetime, now: datetime) -> int:
    """Function to calculate the number of seconds until the SSL certificate expires"""
    return int((expiry_date - now).total_seconds())


def get_expiry_delta_for_hostnames(
    hostnames: list[str], now: datetime
) -> dict[(str, int), int]:
    """Function to calculate the number of seconds until the SSL certificate expires for a list of hostnames"""
    expiry_delta = {}
    for hostname in hostnames:
        _hostname, _port = set_host_port_from_hostname(hostname)
        cert_expiry = evaluate_hostname_cert_expiry(_hostname, _port)
        if cert_expiry:
            expiry_delta[(_hostname, _port)] = get_expiry_delta_in_seconds(
                cert_expiry,
                now,
            )
        else:
            print(
                "Skipping {}:{} : Not able to retrieve valid SSL Certificate data".format(
                    _hostname, _port
                )
            )
    return expiry_delta


def set_host_port_from_hostname(hostname: str) -> (str, int):
    """
    Returns the hostname and port from the hostname string given.
    Tries to map to port if port not provided based on well-known scheme
    """
    if not HOSTNAME_RE.match(hostname):
        raise ValueError(f"{hostname}: Invalid hostname")
    compiled_hostname = HOSTNAME_RE.match(hostname)
    _hostname = compiled_hostname.group("hostname")
    _port = compiled_hostname.group("port")
    if _port:
        _port = int(_port)
    _scheme = compiled_hostname.group("scheme")
    print(_hostname, _port, _scheme)
    if not _scheme and not _port:
        raise ValueError(f"{hostname}: Could not determine port (no scheme, no port)")
    if _hostname and _port:
        return _hostname, _port
    elif _scheme and not _port:
        if _scheme in KNOWN_SCHEMES:
            return _hostname, KNOWN_SCHEMES[_scheme]
        else:
            raise ValueError(
                f"{hostname}: Could not determine port from scheme and no port with schemes ({KNOWN_SCHEMES})"
            )

    else:
        raise ValueError(f"{hostname}: Could not determine port for")


def generate_cloudwatch_metrics_per_hostname(
    hostnames: dict[(str, int), int]
) -> list[dict]:
    """Function to generate CloudWatch metrics for a list of hostnames"""
    metrics = []
    for hostname, expiry_delta in hostnames.items():
        metrics.append(
            {
                "MetricName": "TimeToExpiry",
                "Dimensions": [
                    {
                        "Name": "Endpoint",
                        "Value": f"{hostname[0]}:{hostname[1]}",
                    },
                ],
                "Timestamp": datetime.utcnow(),
                "Value": expiry_delta,
                "Unit": "Seconds",
            }
        )
    return metrics


def publish_cloudwatch_metrics(
    metrics: list[dict], cloudwatch_namespace: str, session: Session
) -> None:
    """Function to publish metrics to AWS CLoudWatch"""
    session = get_session(session)
    cloudwatch = session.client("cloudwatch")
    for _metrics in chunked_iterable(metrics, 1000):
        try:
            cloudwatch.put_metric_data(
                Namespace=cloudwatch_namespace,
                MetricData=_metrics,
            )
        except cloudwatch.exceptions.InvalidParameterValueException as e:
            print(e)


def report_expiry_metrics(hosts: list[str], namespace: str, session: Session) -> None:
    hosts_expiry = get_expiry_delta_for_hostnames(hosts, datetime.utcnow())
    if not hosts_expiry:
        return None
    metrics = generate_cloudwatch_metrics_per_hostname(hosts_expiry)
    publish_cloudwatch_metrics(metrics, namespace, session)
