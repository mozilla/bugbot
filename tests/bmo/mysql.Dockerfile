# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

# MySQL (the version of BMO's production) with libfaketime, to move its clock
# to the time of each scenario.

FROM oraclelinux:9 AS faketime
RUN dnf install -y gcc make git \
    && git clone --depth 1 --branch v0.9.10 https://github.com/wolfcw/libfaketime /src \
    && make -C /src/src FAKETIME_COMPILE_CFLAGS="-DFAKE_STATELESS"

FROM mysql:8.0.42
COPY --from=faketime /src/src/libfaketime.so.1 /usr/local/lib/faketime/libfaketime.so.1
# As in BMO's docker/mysql/bmo.cnf.
RUN printf '[mysqld]\nmax_allowed_packet = 64M\n\n[mysql]\nmax_allowed_packet = 64M\n' > /etc/mysql/conf.d/bmo.cnf
