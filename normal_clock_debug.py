from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from attendance_auth_client import ApiError, AttendanceAuthClient, AuthError

DEFAULT_LONGITUDE = ""
DEFAULT_LATITUDE = ""


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
    address: Optional[str] = None,
    today: Optional[str] = None,
    image: Optional[Path] = None,
    submit: bool = False,
    no_address: bool = False,
) -> dict[str, Any]:
    token = _require_cached_session(client)
    today = today or date.today().isoformat()
    longitude = str(longitude or "").strip()
    latitude = str(latitude or "").strip()
    if not longitude or not latitude:
        raise ValueError("未配置打卡经纬度，请先通过 xlsx 导入纬度和经度。")

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
    configured_address = str(address or "").strip()
    submit_address = None if no_address else (configured_address or range_address or None)

    result: dict[str, Any] = {
        "mode": "submit" if submit else "dry-run",
        "productionWritePerformed": False,
        "location": {
            "longitude": longitude,
            "latitude": latitude,
            "configuredAddress": configured_address,
            "rangeAddress": range_address,
            "submitAddress": submit_address,
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
                "当前 H5 会拦截未录入人脸或不在考勤范围内的场景。",
                "接口层已确认 imgPath 是硬依赖，address 建议一并传入。",
                "目前没有安全证据能证明服务端完全不做人脸校验，因此不要把“可绕过”当成定论。",
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
        if submit_address:
            submit_body["address"] = submit_address
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
            "address": submit_address,
        }

    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="正常打卡调试脚本。默认只读取状态和上传图片，不会直接写入真实打卡记录。",
    )
    parser.add_argument(
        "--image",
        type=Path,
        help="本地人像图片路径。传入后会尝试调用 attendanceImage/file 上传。",
    )
    parser.add_argument(
        "--longitude",
        default=DEFAULT_LONGITUDE,
        help="普通经度。未提供时不会再使用内置固定坐标。",
    )
    parser.add_argument(
        "--latitude",
        default=DEFAULT_LATITUDE,
        help="普通纬度。未提供时不会再使用内置固定坐标。",
    )
    parser.add_argument(
        "--today",
        default=date.today().isoformat(),
        help="要查询的打卡日期，格式为 YYYY-MM-DD。",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="显式执行 createSignRecord。未传时只输出 wouldSubmit，不会落真实记录。",
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
    except (AuthError, ApiError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
