"""Validation for the values the configuration window writes to the system.

Everything typed in the configuration window ends up in rc.conf or
/etc/resolv.conf. sysrc writes a value between double quotes without
escaping it, and rc.conf is a shell script that runs as root at boot, so a
value holding a quote, $(...) or a backtick would run as root. These checks
only let through what each field can legitimately hold and return it in a
normalized form. Anything else raises ValueError with a message for the user.
"""

import re
from ipaddress import IPv4Address, IPv4Network, IPv6Address

# FreeBSD interface names such as em0, wlan0, epair0a or em0.10. Renamed
# interfaces can be almost anything, so this only keeps to the characters
# that are safe in rc.conf and to IFNAMSIZ, 15 characters plus the NUL.
INTERFACE_REGEX = re.compile(r'[A-Za-z][A-Za-z0-9_.]{0,14}')
# One DNS label: letters, digits and inner hyphens, at most 63 characters.
LABEL_REGEX = re.compile(r'(?!-)[A-Za-z0-9-]{1,63}(?<!-)')
# resolv.conf(5) honours at most six search domains in 256 characters.
MAX_SEARCH_DOMAINS = 6
MAX_SEARCH_LENGTH = 256
# A prefix length. str.isdigit() would also take digits such as "²".
PREFIX_REGEX = re.compile(r'[0-9]{1,3}')
# rc.subr turns these characters of an interface name into "_" when it
# looks up ifconfig_<name> and friends. See get_if_var in network.subr.
RC_CONF_PUNCTUATION = str.maketrans('.-/+', '____')


def interface(name):
    """
    Check an interface name.

    Args:
        name (str): the interface, for instance "em0".

    Returns:
        str: the name unchanged.

    Raises:
        ValueError: when it is not a plain FreeBSD interface name.
    """
    if not INTERFACE_REGEX.fullmatch(name):
        raise ValueError(f'"{name}" is not a valid interface name.')
    return name


def rc_conf_interface(name):
    """
    Give the form of an interface name that rc.conf variables use.

    rc.subr reads the settings of em0.10 from ifconfig_em0_10, and sysrc
    refuses a variable name with a dot in it.

    Args:
        name (str): the interface, for instance "em0.10".

    Returns:
        str: the name with ".", "-", "/" and "+" replaced by "_".
    """
    return name.translate(RC_CONF_PUNCTUATION)


def ipv4_address(text, field):
    """
    Check an IPv4 address.

    Args:
        text (str): what the user typed.
        field (str): the field's label, used in the error message.

    Returns:
        str: the address in dotted-decimal form.

    Raises:
        ValueError: when the text is not an IPv4 address.
    """
    try:
        return str(IPv4Address(text.strip()))
    except ValueError:
        raise ValueError(f'{field}: "{text}" is not a valid IPv4 address.') from None


def ipv4_netmask(text):
    """
    Check an IPv4 netmask, given dotted or as a prefix length.

    Args:
        text (str): "255.255.255.0" or "24".

    Returns:
        str: the netmask in dotted-decimal form, as ifconfig and rc.conf
            expect it.

    Raises:
        ValueError: when the text is neither a contiguous dotted netmask
            nor a prefix length from 1 to 32. A zero netmask would put the
            whole internet on the link, so it is refused.
    """
    value = text.strip()
    error = ValueError(f'Subnet Mask: "{text}" is not a valid netmask.')
    if PREFIX_REGEX.fullmatch(value):
        if not 1 <= int(value) <= 32:
            raise error
        return str(IPv4Network(f'0.0.0.0/{value}').netmask)
    try:
        mask = IPv4Address(value)
        # IPv4Network also takes host masks such as 0.0.0.255, so check
        # that the netmask it derives is the one that was typed.
        if IPv4Network(f'0.0.0.0/{value}').netmask != mask \
                or mask == IPv4Address('0.0.0.0'):
            raise error
    except ValueError:
        raise error from None
    return str(mask)


def ipv6_address(text, field, allow_scope=False):
    """
    Check an IPv6 address.

    Args:
        text (str): what the user typed.
        field (str): the field's label, used in the error message.
        allow_scope (bool): accept a "%interface" zone, as a link-local
            gateway needs.

    Returns:
        str: the address in compressed form, with its zone if it had one.

    Raises:
        ValueError: when the text is not an IPv6 address, or carries a zone
            that is not allowed or is not an interface name.
    """
    value = text.strip()
    error = ValueError(f'{field}: "{text}" is not a valid IPv6 address.')
    address, _, scope = value.partition('%')
    if scope or value.endswith('%'):
        if not allow_scope or not INTERFACE_REGEX.fullmatch(scope):
            raise error
    try:
        normalized = str(IPv6Address(address))
    except ValueError:
        raise error from None
    return f'{normalized}%{scope}' if scope else normalized


def ip_address(text, field):
    """
    Check an IPv4 or IPv6 address, as a nameserver line accepts either.

    Args:
        text (str): what the user typed.
        field (str): the field's label, used in the error message.

    Returns:
        str: the normalized address.

    Raises:
        ValueError: when the text is neither.
    """
    try:
        return ipv4_address(text, field)
    except ValueError:
        pass
    try:
        return ipv6_address(text, field)
    except ValueError:
        raise ValueError(f'{field}: "{text}" is not a valid IP address.') from None


def ipv6_prefixlen(text):
    """
    Check an IPv6 prefix length.

    Args:
        text (str): what the user typed, for instance "64".

    Returns:
        str: the prefix length without leading zeros.

    Raises:
        ValueError: when it is not a whole number from 1 to 128.
    """
    value = text.strip()
    if not PREFIX_REGEX.fullmatch(value) or not 1 <= int(value) <= 128:
        raise ValueError(f'Prefix Length: "{text}" must be a number from 1 to 128.')
    return str(int(value))


def search_domains(text):
    """
    Check a space separated list of search domains.

    Args:
        text (str): what the user typed, for instance "example.org lan".

    Returns:
        str: the domains joined by single spaces, empty if none were given.

    Raises:
        ValueError: when a domain is not a valid DNS name, or the list is
            longer than resolv.conf accepts.
    """
    domains = text.split()
    for domain in domains:
        # One trailing dot marks a fully qualified name. Only that one is
        # dropped, so "example.com.." leaves an empty label and is refused.
        labels = domain.removesuffix('.').split('.')
        if len(domain) > 253 or not all(LABEL_REGEX.fullmatch(label) for label in labels):
            raise ValueError(f'Search domains: "{domain}" is not a valid domain name.')
    joined = ' '.join(domains)
    if len(domains) > MAX_SEARCH_DOMAINS or len(joined) > MAX_SEARCH_LENGTH:
        raise ValueError(
            f'Search domains: at most {MAX_SEARCH_DOMAINS} domains '
            f'and {MAX_SEARCH_LENGTH} characters are allowed.'
        )
    return joined
