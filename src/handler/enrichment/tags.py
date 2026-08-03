from __future__ import annotations

import dataclasses

import boto3

from .. import logging as structured_log
from ..config import Config
from ..events import HealthEvent


def format_pairs(d: dict[str, str]) -> str:
    return ", ".join(f"{k}={v}" for k, v in d.items())


def fetch(
    account: str, region: str, instance_ids: list[str], cfg: Config
) -> dict[str, dict[str, str]]:
    try:
        sts = boto3.client("sts")
        role_arn = f"arn:aws:iam::{account}:role/{cfg.describe_role_name}"
        creds = sts.assume_role(RoleArn=role_arn, RoleSessionName="aws-health-notifier")[
            "Credentials"
        ]
        ec2 = boto3.client(
            "ec2",
            region_name=region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
        reservations = ec2.describe_instances(InstanceIds=instance_ids)["Reservations"]
        wanted = set(cfg.tag_keys)
        out: dict[str, dict[str, str]] = {}
        for reservation in reservations:
            for inst in reservation["Instances"]:
                iid = inst["InstanceId"]
                out[iid] = {
                    t["Key"]: t["Value"] for t in inst.get("Tags", []) if t["Key"] in wanted
                }
        return out
    except Exception as exc:  # noqa: BLE001  best-effort: never block a ticket
        structured_log.emit("enrich-failed", account, region=region, error=str(exc))
        return {}


def with_tags(ev: HealthEvent, cfg: Config) -> HealthEvent:
    if not cfg.enrich_tags or not ev.entities:
        return ev
    return dataclasses.replace(ev, instance_tags=fetch(ev.account, ev.region, ev.entities, cfg))
