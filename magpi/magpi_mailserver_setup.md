# MagPi Mail Server Setup
**Server:** 192.168.1.100 (magpi server / relay host)  
**Purpose:** Accept mail from all MagPi boxes on 192.168.1.x and relay to external SMTP  
**Default recipient:** tgentner@ucsd.edu

---

## Overview

Each MagPi Pi (192.168.1.x) is configured as a postfix **satellite** — it sends all mail to
192.168.1.100, which acts as the **relay host**. The relay host forwards mail onward to an
external SMTP server for final delivery.

```
MagPi box (192.168.1.1)
    └─→ postfix satellite
            └─→ 192.168.1.100 (relay host)
                    └─→ UCSD SMTP (smtp.ucsd.edu) or Gmail
                            └─→ tgentner@ucsd.edu
```

---

## 1. Install postfix on the server

```bash
sudo apt-get update
sudo apt-get install -y postfix mailutils
```

During the interactive setup, select **"Internet Site"** and enter the server's hostname.

---

## 2. Configure postfix as a relay host

Edit `/etc/postfix/main.cf`:

```bash
sudo nano /etc/postfix/main.cf
```

Set the following values (add or replace as needed):

```ini
# Server identity
myhostname = magpiserver.local
mydomain = local
myorigin = $myhostname

# Accept mail from localhost and local MagPi subnet
inet_interfaces = all
inet_protocols = ipv4

# Do not deliver locally — relay everything outbound
mydestination = $myhostname, localhost.$mydomain, localhost
mynetworks = 127.0.0.0/8, 192.168.1.0/24

# Relay outbound mail through UCSD SMTP
# (see Section 3 for Gmail alternative)
relayhost = [smtp.ucsd.edu]:587

# Allow the MagPi subnet to relay through this server
smtpd_relay_restrictions =
    permit_mynetworks,
    reject_unauth_destination

# TLS for outbound relay (required by most SMTP servers)
smtp_tls_security_level = encrypt
smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt

# SASL authentication for outbound relay
smtp_sasl_auth_enable = yes
smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd
smtp_sasl_security_options = noanonymous
smtp_sasl_tls_security_options = noanonymous
```

---

## 3. Configure outbound SMTP credentials

### Option A: UCSD SMTP (smtp.ucsd.edu)

Check with UCSD IT for the correct relay settings. UCSD may allow relay from on-campus
IP ranges without authentication, or may require AD credentials.

Create `/etc/postfix/sasl_passwd`:

```
[smtp.ucsd.edu]:587    your-ucsd-username@ucsd.edu:your-password
```

### Option B: Gmail SMTP

Requires a Gmail **App Password** (not your regular password).
To generate one: Google Account → Security → 2-Step Verification → App Passwords.

Create `/etc/postfix/sasl_passwd`:

```
[smtp.gmail.com]:587    tgentner@gmail.com:your-app-password
```

Update `main.cf`:
```ini
relayhost = [smtp.gmail.com]:587
```

### After creating sasl_passwd (both options):

```bash
sudo chmod 600 /etc/postfix/sasl_passwd
sudo postmap /etc/postfix/sasl_passwd
sudo systemctl restart postfix
```

---

## 4. Set up sender address rewriting (optional but recommended)

By default, mail from a MagPi will arrive as `bird@magpi00.local`, which most SMTP
servers will reject. Map all outgoing addresses to `tgentner@ucsd.edu`:

Create `/etc/postfix/sender_canonical`:

```
bird@magpi00.local    tgentner@ucsd.edu
@magpi00.local        tgentner@ucsd.edu
```

Or to catch all MagPi boxes at once:

```
/.*/    tgentner@ucsd.edu
```

Add to `main.cf`:

```ini
sender_canonical_maps = regexp:/etc/postfix/sender_canonical
```

Then:

```bash
sudo postmap /etc/postfix/sender_canonical
sudo systemctl restart postfix
```

---

## 5. Enable and start postfix

```bash
sudo systemctl enable postfix
sudo systemctl start postfix
```

---

## 6. Test the relay

### From the server itself:

```bash
echo "Test from magpi server" | mail -s "postfix relay test" tgentner@ucsd.edu
```

Check the mail log:

```bash
sudo tail -f /var/log/mail.log
```

### From a MagPi box (192.168.1.1):

```bash
echo "Test from magpi00" | mail -s "magpi00 relay test" tgentner@ucsd.edu
```

Check the log on the Pi:

```bash
sudo tail -f /var/log/mail.log
```

### Expected log output (success):

```
postfix/smtp[xxxx]: ... relay=smtp.ucsd.edu[...]:587, status=sent (250 OK)
```

---

## 7. Troubleshooting

| Symptom | Check |
|---|---|
| Mail stuck in queue | `mailq` — shows queued messages |
| Force retry | `sudo postfix flush` |
| View full log | `sudo tail -100 /var/log/mail.log` |
| Test SMTP connection | `telnet 192.168.1.100 25` from a MagPi |
| Check postfix config | `sudo postconf -n` |
| Relay rejected | Check `mynetworks` includes 192.168.1.0/24 |
| TLS error | Check `smtp_tls_CAfile` path is correct |

---

## 8. Firewall

If the server has a firewall (ufw), allow SMTP from the MagPi subnet:

```bash
sudo ufw allow from 192.168.1.0/24 to any port 25
sudo ufw reload
```

---

## Summary checklist

- [ ] postfix installed on 192.168.1.100
- [ ] `mynetworks` includes 192.168.1.0/24
- [ ] `relayhost` set to upstream SMTP server
- [ ] `sasl_passwd` created and `postmap`ed
- [ ] Sender canonical rewriting configured
- [ ] Port 25 open from MagPi subnet
- [ ] Test mail received at tgentner@ucsd.edu
