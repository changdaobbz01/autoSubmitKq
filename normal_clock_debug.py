from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from attendance_auth_client import ApiError, AttendanceAuthClient, AuthError

DEFAULT_LONGITUDE = "114.24549825716642"
DEFAULT_LATITUDE = "30.608913948312445"


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _response_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "isSuccess": payload.get("isSuccess"),
        "retCode": payload.get("retCode"),
        "retMsg": payload.get("retMsg"),
        "retContent": payload.get("retContent"),
    }


def _require_cached_session(client: AttendanceAuthClient) -> str:
    session = client.get_cached_session(validate_with_server=True)
    if session is None:
        raise AuthError("本地没有可复用 token。请先执行 `python attendance_auth_client.py ensure`。")
    return session.token


def run_normal_clock_check(
    client: AttendanceAuthClient,
    *,
    longitude: str = DEFAULT_LONGITUDE,
    latitude: str = DEFAULT_LATITUDE,
    today: Optional[str] = None,
    image: Optional[Path] = None,
    submit: bool = False,
    no_address: bool = False,
) -> dict[str, Any]:
    token = _require_cached_session(client)
    today = today or date.today().isoformat()

    model_payload = client.call_api(
        path="/attendanceImage/searchModel",
        method="POST",
        token=token,
        body={},
    )
    address_payload = client.call_api(
        path="/adPhoneSignrecordDic/getSignAddress",
        method="POST",
        token=token,
        body={"longitude": longitude, "latitude": latitude},
    )
    records_payload = client.call_api(
        path="/moSignRecord/getSignCord",
        method="GET",
        token=token,
        params={"nowtime": today},
    )

    has_face_model = bool(model_payload.get("retContent"))
    range_address = address_payload.get("retContent") or ""

    result: dict[str, Any] = {
        "mode": "submit" if submit else "dry-run",
        "productionWritePerformed": False,
        "location": {
            "longitude": longitude,
            "latitude": latitude,
            "rangeAddress": range_address,
            "inRange": bool(range_address),
            "signAddressResponse": _response_summary(address_payload),
        },
        "faceModel": {
            "configured": has_face_model,
            "response": _response_summary(model_payload),
        },
        "todayRecords": _response_summary(records_payload),
        "h5Gate": {
            "hasFaceModel": has_face_model,
            "inRange": bool(range_address),
            "canOpenClockCamera": has_face_model and bool(range_address),
        },
        "apiGate": {
            "imgPathRequired": True,
            "addressRecommended": bool(range_address),
            "canBypassH5Guard": False,
            "notes": [
                "当前 H5 明确会拦截未录入人脸或不在考勤范围的场景。",
                "接口层已确认 imgPath 是硬依赖，address 建议传。",
                "目前没有安全证据证明服务端完全不做人脸校验，因此不要把“可绕过”当成定论。",
            ],
        },
    }

    upload_path = ""
    if image:
        upload_payload = client.upload_file(
            path="/attendanceImage/file?uploadType=2",
            file_path=image,
            token=token,
            field_name="fileData",
            filename="face.png",
        )
        upload_path = str(upload_payload.get("retContent") or "")
        result["imageUpload"] = {
            "source": str(image),
            "uploaded": bool(upload_path),
            "imgPath": upload_path,
            "response": _response_summary(upload_payload),
        }

        submit_body: dict[str, Any] = {}
        if upload_path:
            submit_body["imgPath"] = upload_path
        if range_address and not no_address:
            submit_body["address"] = range_address
        result["wouldSubmit"] = submit_body

        if submit:
            submit_payload = client.call_api(
                path="/moSignRecord/createSignRecord",
                method="POST",
                token=token,
                body=submit_body,
            )
            result["productionWritePerformed"] = True
            result["submitResponse"] = _response_summary(submit_payload)
    else:
        result["imageUpload"] = {
            "source": None,
            "uploaded": False,
            "imgPath": None,
            "response": None,
        }
        result["wouldSubmit"] = {
            "imgPath": None,
            "address": None if no_address else range_address or None,
        }

    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="正常打卡调试脚本。默认只做读取和图片上传，不会调用真实打卡写接口。",
    )
    parser.add_argument(
        "--image",
        type=Path,
        help="本地人像图片路径。传入后会尝试调用 attendanceImage/file 上传。",
    )
    parser.add_argument(
        "--longitude",
        default=DEFAULT_LONGITUDE,
        help="普通经度。默认使用当前已验证过的航天花园坐标。",
    )
    parser.add_argument(
        "--latitude",
        default=DEFAULT_LATITUDE,
        help="普通纬度。默认使用当前已验证过的航天花园坐标。",
    )
    parser.add_argument(
        "--today",
        default=date.today().isoformat(),
        help="要查询的打卡日期，格式 YYYY-MM-DD。",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="显式执行 createSignRecord。未传时只输出 wouldSubmit，不会落生产记录。",
    )
    parser.add_argument(
        "--no-address",
        action="store_true",
        help="提交时不带 address。仅用于验证最小请求体，不建议生产使用。",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    client = AttendanceAuthClient()

    try:
        result = run_normal_clock_check(
            client,
            longitude=args.longitude,
            latitude=args.latitude,
            today=args.today,
            image=args.image,
            submit=args.submit,
            no_address=args.no_address,
        )
        _print_json(result)
        return 0
    except (AuthError, ApiError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
