# Third-Party Notices

The v1.0.0-beta.1 Windows binary was built with the direct components below. Each component remains under its own license; it is not relicensed under AudioFerry's MIT license. The complete direct and transitive dependency list is in `THIRD_PARTY_INVENTORY.md`.

| Component | Version | Purpose | License | Source |
|---|---:|---|---|---|
| pyatv | 0.17.0 | AirPlay/RAOP discovery and streaming | MIT | https://github.com/postlund/pyatv |
| SoundCard | 0.4.6 | Windows WASAPI loopback capture | BSD-3-Clause | https://github.com/bastibe/SoundCard |
| NumPy | 2.2.6 | PCM sample conversion | BSD-3-Clause | https://github.com/numpy/numpy |
| pystray | 0.19.5 | Windows notification-area icon | LGPL-3.0 | https://github.com/moses-palmer/pystray |
| Pillow | 12.0.0 | Tray icon image | MIT-CMU | https://github.com/python-pillow/Pillow |
| zeroconf | 0.149.16 | mDNS/DNS-SD discovery (transitive/direct packaging dependency) | LGPL-2.1-or-later | https://github.com/python-zeroconf/python-zeroconf |
| PyInstaller | 6.20.0 | Build-time Windows packaging only | GPL-2.0-or-later with bootloader exception | https://github.com/pyinstaller/pyinstaller |

The MIT license is suitable for AudioFerry's original source. The LGPL components do not prevent open-source publication, but binary redistributors must preserve their notices, license texts, and applicable LGPL rights. Exact license texts shipped with the build are in `third_party_licenses/`. NumPy and other packages can include bundled subcomponents; consult the corresponding included license files before redistributing a modified dependency set.

Apple, AirPlay, and HomePod are trademarks of Apple Inc. AudioFerry is independent and is not affiliated with or endorsed by Apple Inc. See `TRADEMARKS.md` for compatibility-reference guidance.
