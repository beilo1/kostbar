# Hardware und Netzwerk

### Hardware je Terminal

| Menge | Bauteil | Ausführung |
| --- | --- | --- |
| 1 | Raspberry Pi 5 | Mit WLAN und Raspberry Pi OS 64-Bit mit Desktop |
| 1 | Raspberry Pi Touch Display 2, 10,1″ Portrait | Artikel `RPI-10LCD2`, nativ 1200 × 1920 Pixel, 1920 × 1200 Pixel im Querformat |
| 1 | Offizielles Raspberry-Pi-USB-C-Netzteil | 27 W, EU-Ausführung |
| 1 | microSD-Karte | 32 GB, vorzugsweise High Endurance |
| 1 | NFC-Leser | ACS ACR1552U-M1 per USB-A, PC/SC-Modus |
| 1 Satz | Gedrucktes Displaygehäuse mit Halteschiene | MakerWorld-Modell `3116241` |

Für diese Displayausführung ist ein **Raspberry Pi 5** vorgesehen. Der Raspberry Pi 4B unterstützt das 10,1-Zoll-Modell nicht. Display und Touch laufen über DSI. Strom bekommt das Display vom Pi über das mitgelieferte GPIO-Kabel. [Raspberry Pi · Display-Spezifikation](https://www.raspberrypi.com/products/touch-display-2/) · [RPI-10LCD2 bei BerryBase](https://www.berry-base.com/en/raspberry-pi-touch-display-2-10.1-portrait) · [Raspberry Pi · 27-W-Netzteil](https://www.raspberrypi.com/products/27w-power-supply/)

### Gehäuse für den Bambu Lab P2S

Verwendet wird das **Raspberry Pi 10.1″ Touch Display 2 Case** von CreationThroughChaos. Lade das Druckprojekt für Modell `3116241` in Bambu Studio und prüfe in der Vorschau, dass Gehäuseschale und Halteschiene auf die P2S-Druckplatten passen. Drucke zunächst einen Satz und prüfe vor weiteren Drucken die Passung von Display und Pi sowie den Platz für das DSI-Kabel, den Stromstecker und die USB-Anschlüsse. Die Gehäuseöffnung bestimmt die Ausrichtung der Displaykabel. [Gehäuse und Druckprofil auf MakerWorld](https://makerworld.com/models/3116241)

### Anschluss und Aufstellung

1. Raspberry Pi OS mit Desktop einrichten. PSK-WLAN, WLAN-Land und ein persönliches Wartungskonto im Raspberry Pi Imager konfigurieren. Betriebssystem und EEPROM des Pi 5 vor der Displaymontage aktualisieren. Danach das produktive WLAN mit Gerätezertifikat einrichten. [Terminal-Anleitung](TERMINALS.md)
2. Den Pi vom Strom trennen. Das mitgelieferte **22-polige Mini-zu-Mini-DSI-Flachbandkabel** zwischen Display und einem der beiden CAM/DISP-Anschlüsse des Pi 5 verbinden. Die Kontaktseite und die Verriegelung nach der Herstelleranleitung für das **10-Zoll-Modell** ausrichten. [Offizielle Montageanleitung](https://www.raspberrypi.com/documentation/accessories/touch-display-2.html#connect-to-a-10-inch-touch-display-2)
3. Das mitgelieferte Stromkabel zwischen Displaybuchse `J1` und GPIO anschließen. Laut Hersteller kommt Rot auf Pin 2 (5 V) und Schwarz auf Pin 6 (GND). Display und Pi in der vorgesehenen Gehäuseposition montieren, ohne das Flachbandkabel einzuklemmen. Erst danach das USB-C-Netzteil anschließen. [Offizielle Montageanleitung mit GPIO-Abbildung](https://www.raspberrypi.com/documentation/accessories/touch-display-2.html#connect-to-a-10-inch-touch-display-2)
4. Den USB-Kartenleser gut erreichbar außerhalb des Gehäuses platzieren. KoSTbar braucht eine stabil lesbare Kartenkennung mit 4 bis 10 Bytes. Die tatsächlich verwendeten Ausweise bzw. Anhänger jeweils durch wiederholtes Abheben und Anhalten an jedem eingerichteten Terminal testen. [ACS · Leserspezifikation](https://www.acs.com.hk/en/products/575/)
5. Das Display im Querformat aufstellen. Der KoSTbar-Autostart dreht `DSI-2` bei jeder grafischen Anmeldung um 270°. Bei **1920 × 1200 Pixeln** mit `KIOSK_SCALE=1.5` beginnen. Das ergibt rund 1280 × 800 CSS-Pixel. Nach dem Neustart an allen vier Ecken die Touch-Zuordnung testen und die Lesbarkeit von Warenkorb, Zahlenfeld und Timeout prüfen.
6. Den verwendeten Hostnamen im internen DNS auf die NAS-LAN-IP setzen. Die Pis und der Admin-PC müssen den Namen auflösen und den HTTPS-Port erreichen können. Bei QNAP ist `kostbar.internal.lan:18443` die Vorgabe. Bei Synology verwendest du den eigenen Hostnamen aus `--origin` auf dem konfigurierten HTTPS-Port. Für die Ersteinrichtung müssen Container-Images und Pakete verfügbar sein. Im Produktivbetrieb verbinden sich die Pis per EAP-TLS mit dem Terminal-VLAN und benötigen internes DNS und HTTPS-Zugriff zum NAS. PayPal läuft optional über das Internet auf dem eigenen Gerät. Bei einem öffentlichen HTTPS-Zertifikat den Verlängerungsweg mit einplanen.
