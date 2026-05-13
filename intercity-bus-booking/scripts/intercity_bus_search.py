#!/usr/bin/env python3
"""Search Tmoney intercity-bus timetables through the official read-only flow.

This helper intentionally stops at timetable parsing. It does not create seat holds,
submit card data, or perform payment.
"""
from __future__ import annotations

import argparse
import html
import http.cookiejar
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from typing import Iterable

BASE_URL = "https://intercitybus.tmoney.co.kr"
ENTRY_PATH = "/otck/trmlInfEnty.do"
TIMETABLE_PATH = "/otck/readAlcnList.do"
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)

ROW_RE = re.compile(r"<tr>\s*(.*?)readSasFeeInf\((.*?)\).*?</tr>", re.DOTALL | re.IGNORECASE)
TD_WRAP_RE = re.compile(r'<div class="td_wrap1">(.*?)</div>', re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
ARG_RE = re.compile(r"'((?:\\'|[^'])*)'")


@dataclass
class Schedule:
    departure_time: str | None
    company: str | None
    duration: str | None
    bus_class: str | None
    adult_fare: str | None
    child_fare: str | None
    student_fare: str | None
    remaining_seats: int | None
    total_seats: int | None
    raw_args: list[str]


def _ssl_context() -> ssl.SSLContext:
    # Tmoney has historically required curl -k in probes on some machines.
    # Keep this helper resilient while limiting it to the official host.
    return ssl._create_unverified_context()  # noqa: SLF001


def _strip(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    value = TAG_RE.sub("", value)
    return html.unescape(value).replace("\xa0", " ").strip()


def _open(opener: urllib.request.OpenerDirector, request: urllib.request.Request, timeout: int) -> str:
    # urllib opener.open does not accept context; HTTPS context must be installed in handler.
    with opener.open(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def build_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=_ssl_context()),
    )


def search_timetable(
    depart_code: str,
    arrive_code: str,
    depart_name: str,
    arrive_name: str,
    date: str,
    time: str = "000000",
    adults: int = 1,
    students: int = 0,
    children: int = 0,
    veterans: int = 0,
    timeout: int = 20,
) -> tuple[str, list[Schedule]]:
    opener = build_opener()
    entry_req = urllib.request.Request(
        f"{BASE_URL}{ENTRY_PATH}",
        headers={"User-Agent": DEFAULT_UA},
        method="GET",
    )
    _open(opener, entry_req, timeout)

    fields = {
        "depr_Trml_Cd": depart_code,
        "arvl_Trml_Cd": arrive_code,
        "depr_Trml_Nm": depart_name,
        "arvl_Trml_Nm": arrive_name,
        "ig": str(adults),
        "im": str(students),
        "ic": str(children),
        "iv": str(veterans),
        "depr_Dt": date,
        "depr_Time": time,
        # Required by the browser JS readAlcnListEntry(). Missing either field
        # returns a generic error page with no schedule rows.
        "bef_Aft_Dvs": "D",
        "req_Rec_Num": "10",
    }
    req = _post_opener_request(f"{BASE_URL}{TIMETABLE_PATH}", fields)
    body = _open(opener, req, timeout)
    return body, parse_schedules(body)


def _post_opener_request(url: str, data: dict[str, str]) -> urllib.request.Request:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    return urllib.request.Request(
        url,
        data=encoded,
        headers={
            "User-Agent": DEFAULT_UA,
            "Referer": f"{BASE_URL}{ENTRY_PATH}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )


def parse_schedules(body: str) -> list[Schedule]:
    schedules: list[Schedule] = []
    for row_html, arg_text in ROW_RE.findall(body):
        args = [a.replace("\\'", "'") for a in ARG_RE.findall(arg_text)]
        cells = [_strip(x) for x in TD_WRAP_RE.findall(row_html)]
        departure = cells[0] if len(cells) > 0 else (args[8][:2] + ":" + args[8][2:4] if len(args) > 8 else None)
        company_cell = cells[1] if len(cells) > 1 else None
        company = args[11] if len(args) > 11 else None
        duration = None
        if company_cell and company and company_cell.startswith(company):
            duration = company_cell[len(company):].strip() or None
        elif company_cell:
            duration = company_cell
        bus_class = args[12] if len(args) > 12 else (cells[2] if len(cells) > 2 else None)
        remaining = int(args[16]) if len(args) > 16 and args[16].isdigit() else None
        total = int(args[17]) if len(args) > 17 and args[17].isdigit() else None
        schedules.append(
            Schedule(
                departure_time=departure,
                company=company,
                duration=duration,
                bus_class=bus_class,
                adult_fare=cells[3] if len(cells) > 3 else None,
                child_fare=cells[4] if len(cells) > 4 else None,
                student_fare=cells[5] if len(cells) > 5 else None,
                remaining_seats=remaining,
                total_seats=total,
                raw_args=args,
            )
        )
    return schedules


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search Tmoney intercity-bus timetable")
    parser.add_argument("--depart-code", required=True)
    parser.add_argument("--arrive-code", required=True)
    parser.add_argument("--depart-name", required=True)
    parser.add_argument("--arrive-name", required=True)
    parser.add_argument("--date", required=True, help="YYYYMMDD")
    parser.add_argument("--time", default="000000", help="HHMMSS, default 000000")
    parser.add_argument("--adults", type=int, default=1)
    parser.add_argument("--students", type=int, default=0)
    parser.add_argument("--children", type=int, default=0)
    parser.add_argument("--veterans", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)

    if not re.fullmatch(r"\d{8}", args.date):
        parser.error("--date must be YYYYMMDD")
    if not re.fullmatch(r"\d{6}", args.time):
        parser.error("--time must be HHMMSS")

    body, schedules = search_timetable(
        depart_code=args.depart_code,
        arrive_code=args.arrive_code,
        depart_name=args.depart_name,
        arrive_name=args.arrive_name,
        date=args.date,
        time=args.time,
        adults=args.adults,
        students=args.students,
        children=args.children,
        veterans=args.veterans,
        timeout=args.timeout,
    )
    result = {
        "route": {
            "depart_code": args.depart_code,
            "arrive_code": args.arrive_code,
            "depart_name": args.depart_name,
            "arrive_name": args.arrive_name,
            "date": args.date,
            "time": args.time,
        },
        "count": len(schedules),
        "items": [asdict(s) for s in schedules[: args.limit]],
        "failure_mode": None,
    }
    if not schedules:
        result["failure_mode"] = (
            "No readSasFeeInf schedule rows found. Check terminal codes/date, sold-out/no-service state, "
            "or whether Tmoney returned its generic error page."
        )
        result["error_page_marker_count"] = body.count("errorCont")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if schedules else 2


if __name__ == "__main__":
    sys.exit(main())
