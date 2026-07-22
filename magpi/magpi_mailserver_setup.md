# MagPi Mail Relay

**Server:** magpi.ucsd.edu (192.168.1.100 on the MagPi subnet, 132.239.182.189 on campus)
**Purpose:** let every MagPi box on 192.168.1.x relay pyoperant's error-notification emails through magpi.ucsd.edu to a real inbox
**Default recipient:** whatever `experimenter.email` a subject's `config.json` sets (`pyoperant/behavior/base.py`'s `SMTPHandler` sets `toaddrs` from that per-behavior-class, no server-side rewriting needed)

---

## How it actually works

```
MagPi box (192.168.1.x)
    └─→ smtplib.SMTP('192.168.1.100')  (pyoperant's SMTP_CONFIG['mailhost'], already set in every local_*.py)
            └─→ magpi.ucsd.edu:25 (accepts, no auth needed -- see below)
                    └─→ relayhost = outbound.ucsd.edu (accepts, no auth needed -- trusted by campus IP)
                            └─→ real inbox
```

magpi.ucsd.edu is a shared, campus-managed host (UCSD's SSCF, config pushed by CFEngine — see `[[reference_magpi_server]]` if you have that memory context, or ask whoever's touched this before). **Postfix is not something the lab installs or configures from scratch** — it's already there, and its config is centrally managed. The only thing that was actually missing was a *network permission*: Postfix's `inet_interfaces`/`mynetworks` were scoped to localhost only, so nothing on the 192.168.1.0/24 subnet could even open a TCP connection to port 25 — every relay attempt got a plain `Connection refused`. Fixed by filing a request with SSCF (confirmed working 2026-07-22) to allow relay from the MagPi subnet; no client-side or lab-side Postfix configuration was needed once that permission was granted.

**Client-side config is already done** — `pyoperant/local_pi.py`, `local_pi_revc.py`, `local_pi_revd.py`, `local_vogel.py`, `local_zog.py` all set `SMTP_CONFIG['mailhost'] = '192.168.1.100'` already. Nothing to change there.

---

## Live config (confirmed 2026-07-22)

```
inet_interfaces = all
mynetworks = 127.0.0.0/8, 192.168.1.0/24
smtpd_relay_restrictions = permit_mynetworks permit_sasl_authenticated defer_unauth_destination
relayhost = outbound.ucsd.edu
myhostname = magpi.ucsd.edu   (system default, not explicitly overridden)
myorigin = /etc/mailname      (contents: magpi.ucsd.edu)
mydestination = $myhostname, $myorigin, localhost.ucsd.edu, localhost
```

**No SASL, no TLS credentials, no sender-address rewriting are configured or needed.** `outbound.ucsd.edu` accepts unauthenticated relay from magpi.ucsd.edu because it's a trusted on-campus IP — this is much simpler than an earlier draft of this doc assumed (that draft described a `smtp.ucsd.edu:587` + SASL-password plan that was never actually built; the real config above is what's live). Mail from `bird@magpi.ucsd.edu` is already a real, deliverable sender address — no `sender_canonical_maps` rewrite needed like you'd need for a fake `.local` domain.

---

## Testing the relay

From magpi itself, targeting its own LAN-facing IP (this exercises the exact path a Pi client uses — `mynetworks`/`inet_interfaces` gate on that interface, not on being the same machine):

```bash
{
echo "EHLO test-client"
sleep 1
echo "MAIL FROM:<bird@magpi.ucsd.edu>"
sleep 1
echo "RCPT TO:<you@ucsd.edu>"
sleep 1
echo "DATA"
sleep 1
echo "Subject: Magpi mail relay test"
echo ""
echo "test body"
echo "."
sleep 1
echo "QUIT"
} | nc 192.168.1.100 25
```

Expect `220` greeting, `250 2.1.0 Ok` / `250 2.1.5 Ok` for `MAIL FROM`/`RCPT TO`, and the message actually arriving. From an actual Pi client, the equivalent smoke test is just running pyoperant's own error-notification path, or the same `nc`/`sendmail` test targeting `192.168.1.100`.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| `Connection refused` from a Pi client | `sudo postconf -n \| grep -E "inet_interfaces\|mynetworks"` on magpi.ucsd.edu — if `inet_interfaces` isn't `all` or `mynetworks` doesn't include `192.168.1.0/24`, the network permission has regressed (this exact thing happened once: a manual fix worked temporarily then got silently reverted within ~10-20 min by CFEngine, because it wasn't landed in the actual managed policy source). File with SSCF again rather than re-applying a live `postconf -e` edit, which won't stick. |
| Mail accepted by magpi but never arrives | `mailq` on magpi.ucsd.edu, `sudo tail -100 /var/log/mail.log`. Since `relayhost = outbound.ucsd.edu` needs no auth, a failure here is more likely an outbound.ucsd.edu-side issue than a magpi config problem. |
| Unsure what's actually configured right now | `sudo postconf -n` on magpi.ucsd.edu is the source of truth — don't trust this doc's "Live config" section blindly if it's been a while, config drift is exactly what caused problems here before. |
| Firewall | This box uses `iptables` (CFEngine-managed, from `generated-firewall/iptables.generic`), not `ufw`. The MagPi subnet already has a blanket `ACCEPT` rule for `192.168.1.0/24` with no port restriction, so firewall is not expected to be the blocker for anything on this subnet. |
