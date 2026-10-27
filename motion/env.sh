# Chromium runtime libs fetched without root (apt-get download + dpkg-deb -x); override with CF_CHROME_LIBS
_cf_libs="${CF_CHROME_LIBS:-$HOME/opt/chromelibs/root/usr/lib/x86_64-linux-gnu:$HOME/opt/chromelibs/root/usr/lib/x86_64-linux-gnu/gbm}"
export LD_LIBRARY_PATH="$_cf_libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
