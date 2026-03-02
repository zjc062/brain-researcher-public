import csv
import json
import os
import re
import urllib.request


DATASET_ID = "ds000105"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")


def post_graphql(query: str) -> dict:
    payload = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "brain_researcher_benchmark",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)
    if data.get("errors"):
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data


def get_json(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": "brain_researcher_benchmark"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


query = f"""
query {{
  dataset(id: "{DATASET_ID}") {{
    id
    latestSnapshot {{
      tag
      files {{
        filename
        directory
      }}
    }}
  }}
}}
"""

graph = post_graphql(query)
dataset = graph["data"]["dataset"]
if not dataset:
    raise RuntimeError(f"Dataset not found: {DATASET_ID}")

snapshot = dataset["latestSnapshot"]
snapshot_tag = snapshot["tag"]

desc_url = (
    f"https://openneuro.org/crn/datasets/{DATASET_ID}/snapshots/"
    f"{snapshot_tag}/files/dataset_description.json"
)
dataset_description = get_json(desc_url)

if "Name" not in dataset_description or "BIDSVersion" not in dataset_description:
    raise RuntimeError("dataset_description.json missing required keys")

dataset_doi = str(dataset_description.get("DatasetDOI", "")).strip().lower()
if not dataset_doi or f"openneuro.{DATASET_ID}" not in dataset_doi:
    raise RuntimeError(f"dataset_description.json invalid DatasetDOI for {DATASET_ID}")

subject_ids = set()
snapshot_files = []
for f in snapshot.get("files", []):
    filename = f.get("filename")
    if not isinstance(filename, str):
        continue
    snapshot_files.append(filename)
    root = filename.split("/", 1)[0]
    if re.fullmatch(r"sub-[A-Za-z0-9]+", root):
        subject_ids.add(root)

subject_ids = sorted(subject_ids)
if not subject_ids:
    raise RuntimeError("No BIDS-style subject IDs found in snapshot file list")

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(
    os.path.join(OUTPUT_DIR, "dataset_description.json"),
    "w",
    encoding="utf-8",
) as f:
    json.dump(dataset_description, f, indent=2, sort_keys=True)
    f.write("\n")

with open(
    os.path.join(OUTPUT_DIR, "participants.tsv"),
    "w",
    encoding="utf-8",
    newline="",
) as f:
    writer = csv.writer(f, delimiter="\t", lineterminator="\n")
    writer.writerow(["participant_id"])
    for sid in subject_ids:
        writer.writerow([sid])

with open(
    os.path.join(OUTPUT_DIR, "openneuro_snapshot_files.json"),
    "w",
    encoding="utf-8",
) as f:
    json.dump(
        {
            "dataset_id": DATASET_ID,
            "snapshot_tag": snapshot_tag,
            "files": sorted(set(snapshot_files)),
        },
        f,
        indent=2,
        sort_keys=True,
    )
    f.write("\n")

print(f"Wrote outputs to {OUTPUT_DIR}")
print(f"Snapshot tag: {snapshot_tag}")
print(f"Discovered participants: {len(subject_ids)}")
