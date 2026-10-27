#!/usr/bin/env python3
"""Download original-quality videos from an iCloud shared album link.

Usage: icloud_fetch.py https://photos.icloud.com/shared/album/<token> [--photos]

Uses the same anonymous CloudKit calls as the photos.icloud.com web page:
resolve the share token -> list the shared zone -> fetch resOriginal files.
Saves into <repo>/raw/, skipping files that already exist.
"""
import base64, json, os, sys, urllib.parse, urllib.request

RAW = os.path.join(os.environ.get("CF_ROOT") or os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "raw")
CK = "https://ckdatabasews.icloud.com/database/1/com.apple.photos.cloud/production"
HDR = {"Content-Type": "text/plain", "Origin": "https://photos.icloud.com"}


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=HDR)
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def main(link, want_photos=False, dest=None):
    dest = dest or RAW
    token = link.rstrip("/").split("/")[-1].split("#")[-1]
    res = post(f"{CK}/public/records/resolve", {"shortGUIDs": [{"value": token}]})["results"][0]
    title = res["share"]["fields"].get("cloudkit.title", {}).get("value", "")
    apa = res["anonymousPublicAccess"]
    qs = urllib.parse.urlencode({"publicAccessAuthToken": apa["token"], "sharing_url_key": token})
    base = apa["databasePartition"].replace(":443", "")
    url = f"{base}/database/1/com.apple.photos.cloud/production/shared/changes/zone?{qs}"

    records, sync = [], None
    while True:
        zone = {"zoneID": res["zoneID"]}
        if sync:
            zone["syncToken"] = sync
        z = post(url, {"zones": [zone]})["zones"][0]
        records += z.get("records", [])
        sync = z.get("syncToken")
        if not z.get("moreComing"):
            break

    masters = [r for r in records if r.get("recordType") == "CPLMaster"]
    print(f"album: {title!r}  items: {len(masters)}")
    os.makedirs(dest, exist_ok=True)
    got = []
    for r in masters:
        f = r["fields"]
        is_video = "movie" in f.get("itemType", {}).get("value", "") or "resVidLargeRes" in f
        if not is_video and not want_photos:
            continue
        name = base64.b64decode(f["filenameEnc"]["value"]).decode() if "filenameEnc" in f else r["recordName"]
        res = "resOriginal"
        # HEIC photos: ffmpeg can't read them, so take Apple's full-size JPEG rendition instead
        if not is_video and "heic" in f.get("resOriginalFileType", {}).get("value", "").lower():
            res = next((k for k in ("resJPEGFull", "resJPEGLarge", "resJPEGMed") if k + "Res" in f), res)
            if res != "resOriginal":
                name = os.path.splitext(name)[0] + ".JPG"
        dst = os.path.join(dest, name)
        if os.path.exists(dst):
            print(f"  skip {name} (exists)")
            continue
        dl = f[res + "Res"]["value"]["downloadURL"].replace("${f}", urllib.parse.quote(name))
        print(f"  get  {name}  {f[res + 'Width']['value']}x{f[res + 'Height']['value']}  "
              f"{f[res + 'FileSize']['value'] / 1e6:.1f} MB")
        urllib.request.urlretrieve(dl, dst + ".part")
        os.replace(dst + ".part", dst)
        got.append(dst)
    return {"title": title, "items": len(masters), "downloaded": got}


if __name__ == "__main__":
    main(sys.argv[1], "--photos" in sys.argv)
