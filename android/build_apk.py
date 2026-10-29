# -*- coding: utf-8 -*-
"""构建安卓悬浮球版 APK（不依赖 Gradle，直接调用 Android SDK build-tools）"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SDK = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")
BT = os.path.join(SDK, "build-tools", "34.0.0")
ANDROID_JAR = os.path.join(SDK, "platforms", "android-34", "android.jar")
BUILD = os.path.join(ROOT, "android", "build")
KS = os.path.join(ROOT, "android", "release.keystore")
PASS = "Lzp520520520"
OUT = os.path.join(ROOT, "dist", "鼠标画笔_安卓版_v1.1.0.apk")


def run(*args):
    print("[RUN]", " ".join(args))
    exe = shutil.which(args[0]) or args[0]
    if subprocess.call([exe] + list(args[1:])) != 0:
        sys.exit("失败: " + args[0])


def main():
    os.chdir(ROOT)
    if os.path.isdir(BUILD):
        shutil.rmtree(BUILD)
    os.makedirs(os.path.join(BUILD, "dex"))
    os.makedirs(os.path.join(BUILD, "classes"))
    run(os.path.join(BT, "aapt2.exe"), "compile", "--dir", "android/res",
        "-o", os.path.join(BUILD, "res.zip"))
    run(os.path.join(BT, "aapt2.exe"), "link",
        "-o", os.path.join(BUILD, "base.apk"), "-I", ANDROID_JAR,
        "--manifest", "android/AndroidManifest.xml",
        os.path.join(BUILD, "res.zip"), "--auto-add-overlay")

    sources = []
    for base, _, files in os.walk(os.path.join("android", "src")):
        for f in files:
            if f.endswith(".java"):
                sources.append(os.path.join(base, f))
    run("javac", "-source", "8", "-target", "8", "-bootclasspath", ANDROID_JAR,
        "-d", os.path.join(BUILD, "classes"), *sources)
    run("jar", "cf", os.path.join(BUILD, "classes.jar"), "-C", os.path.join(BUILD, "classes"), ".")
    run(os.path.join(BT, "d8.bat"), "--release", "--lib", ANDROID_JAR, "--min-api", "21",
        "--output", os.path.join(BUILD, "dex"), os.path.join(BUILD, "classes.jar"))

    import zipfile
    with zipfile.ZipFile(os.path.join(BUILD, "base.apk"), "a", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(BUILD, "dex", "classes.dex"), "classes.dex")

    run(os.path.join(BT, "zipalign.exe"), "-f", "-p", "4",
        os.path.join(BUILD, "base.apk"), os.path.join(BUILD, "aligned.apk"))

    if not os.path.exists(KS):
        run("keytool", "-genkeypair", "-keystore", KS, "-alias", "screenpen",
            "-keyalg", "RSA", "-keysize", "2048", "-validity", "36500",
            "-storepass", PASS, "-keypass", PASS,
            "-dname", "CN=ecojia.cn, OU=Tools, O=JunGe, L=Chengdu, ST=Sichuan, C=CN")

    run(os.path.join(BT, "apksigner.bat"), "sign", "--ks", KS,
        "--ks-pass", "pass:" + PASS, "--key-pass", "pass:" + PASS,
        "--min-sdk-version", "21", "--out", OUT,
        os.path.join(BUILD, "aligned.apk"))
    idsig = OUT + ".idsig"
    if os.path.exists(idsig):
        os.remove(idsig)
    print("完成:", OUT, round(os.path.getsize(OUT) / 1024.0, 1), "KB")


if __name__ == "__main__":
    main()
