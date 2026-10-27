"""Post-render pieces: thumbnails, audio mastering, frame checks (flash safety)."""
import subprocess

from PIL import Image

from factory import engines, qa, thumbs


def test_thumbnail_designs_have_the_canvas_size(tmp_path):
    im = Image.new("RGB", (720, 1280), (40, 90, 160))
    for v, size in (("A", (1280, 720)), ("B", (1080, 1920)), ("C", (1280, 720))):
        out = thumbs.design(im, "This lake looks unreal", v, size, (255, 217, 61), lang="en")
        assert out.size == size
    assert thumbs.words_of("istanbul ışık", "tr") == ["İSTANBUL", "IŞIK"]
    a, b = Image.new("RGB", (64, 64), (128, 128, 128)), Image.effect_noise((64, 64), 80).convert("RGB")
    assert [t for t, _ in thumbs.pick([(1.0, a), (5.0, b)], k=1)] == [5.0]   # the detailed frame wins


def test_master_brings_a_quiet_mix_to_target(tmp_path):
    f = str(tmp_path / "q.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=3", "-f", "lavfi",
                    "-i", "sine=f=300:d=3,volume=0.05", "-c:v", "libx264", "-c:a", "aac", "-shortest", f], check=True)
    before, _ = engines.loudness(f)
    r = engines.master(f)
    assert before < -30 and r["changed"] and abs(r["lufs"] - engines.TARGET_LUFS) <= 1.0 and r["tp"] <= -1.0


def test_flash_check_flags_strobing(tmp_path):
    f = str(tmp_path / "s.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=96x160:d=3", "-vf",
                    "geq=lum='if(lt(mod(T*8,1),0.5),30,220)':cb=128:cr=128", f], check=True)
    assert qa.frame_checks(f)["flash_windows"]
