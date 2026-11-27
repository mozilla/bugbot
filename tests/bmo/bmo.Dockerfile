# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

# BMO with libfaketime, to move its clock to the time of each scenario.

FROM debian:trixie AS faketime
RUN apt-get update && apt-get install -y gcc make git \
    && git clone --depth 1 --branch v0.9.10 https://github.com/wolfcw/libfaketime /src \
    && make -C /src/src FAKETIME_COMPILE_CFLAGS="-DFAKE_STATELESS"

FROM bmo-base
USER root
COPY --from=faketime /src/src/libfaketime.so.1 /usr/local/lib/faketime/libfaketime.so.1
# Perl has the cap_net_bind_service capability, which makes glibc ignore
# LD_PRELOAD (secure-execution mode). Copying the binary drops it, and BMO
# listens on 8000 anyway.
RUN cp -p /usr/local/bin/perl /tmp/perl && mv /tmp/perl /usr/local/bin/perl
USER app
