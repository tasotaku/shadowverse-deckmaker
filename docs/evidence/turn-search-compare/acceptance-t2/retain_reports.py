"""Preserve small public reports without relocating large candidate payloads."""
import hashlib
import json
import pathlib
import shutil

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT / "output/turn-search-acceptance-t2"
DEST = HERE / "public-artifacts"

def main():
    index = {"reference_rule":"These JSON files are byte-identical copies. Relative report_path/result_path fields inside copied JSON resolve from original_reference_base, NOT from the copied file location. Large result.json files remain in output. All paths in this index are repository-relative.","files":[]}
    for suite in ["medium", "heldout", "hard"]:
        base = OUT / suite
        paths = [base / "summary.json", base / "manifest.json"] + sorted(base.glob("case-*/*/*/report.json"))
        for source in paths:
            if not source.exists():
                continue
            destination = DEST / suite / source.relative_to(base)
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,destination)
            row = {"preserved_copy":str(destination.relative_to(ROOT)),"original_path":str(source.relative_to(ROOT)),"original_reference_base":str(base.relative_to(ROOT)),"sha256":hashlib.sha256(source.read_bytes()).hexdigest()}
            value=json.loads(source.read_text(encoding="utf-8"))
            if "result_path" in value:
                row["resolved_result_path"]=str((base/value["result_path"]).relative_to(ROOT))
            index["files"].append(row)
    (DEST / "index.json").write_text(json.dumps(index,indent=2)+"\n",encoding="utf-8")
    (DEST / "README.md").write_text("# Preserved public benchmark metadata\n\nThese are byte-identical copies of the CLI summary, manifest, and measured/warmup reports. Large candidate `result.json` files remain under `output/turn-search-acceptance-t2`.\n\n**Resolve every copied JSON file's relative `result_path` and `report_path` from the `original_reference_base` in [index.json](index.json), not from this copied location.** The index includes repository-relative original and copy paths, resolved result paths, and SHA256 hashes. Exact suite commands remain in [execution-record.json](../execution-record.json); measured result hashes and paths are in [raw-artifacts.json](../raw-artifacts.json).\n",encoding="utf-8")
    print(json.dumps({"copied_small_artifacts":len(index["files"]),"index":str(DEST / "index.json")}))

if __name__=="__main__":
    main()
