import pytz
from datetime import datetime as dt, tzinfo

NOW = dt.now(tz=pytz.utc)


def get_timezone_code(tz: tzinfo = pytz.utc) -> str:
    return tz.normalize(NOW).strftime("%Z")


def match(z: str = ""):
    def compare(y: str):
        tz = pytz.timezone(y)

        zone = tz.zone
        return z.title().replace(" ", "_") in [zone, zone.split("/")[-1]] or get_timezone_code(tz) == z
    return compare


KNOWN = {}
reverse_countries = dict((pytz.country_names.get(x), x)
                         for x in pytz.country_names)
zone_to_name = {}
for country, code in reverse_countries.items():
    for zone in pytz.country_timezones.get(code, []):
        zone_to_name[zone] = country


def find_timezones(z: str) -> tzinfo:
    if z in KNOWN:
        return [z]

    if z in pytz.all_timezones:
        return [z]

    return list(filter(match(z), pytz.common_timezones)) or list(filter(match(z), pytz.all_timezones))


def best_zone(z=""):
    up, title = z.upper(), z.title()

    if up in pytz.country_timezones:
        zones = [pytz.country_timezones.get(up)[0]]
    elif title in reverse_countries:
        zones = [pytz.country_timezones.get(reverse_countries.get(title))[0]]
    else:
        zones = find_timezones(z)

    best, name = None, None
    if zones:
        if len(zones) == 1:
            best = zones[0]
        if len(zones) > 1:
            if not best:
                best = next(
                    filter(lambda t: t in pytz.country_names, zones), None)
            if best:
                pass
            else:
                name = ', '.join(
                    {t.split("/")[-1].replace('_', ' ') for t in zones})
                best = zones[-1]

        tz = pytz.timezone(best)
        name = zone_to_name.get(best, tz.zone.split("/")[-1].replace("_", " "))

        return tz, name.strip()
    return [None, None]


def format_tz(date: dt) -> str:
    return date.strftime("%d-%b-%Y %H:%M:%S %Z").strip()