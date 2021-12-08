# Alarmierung über Groupalarm.com auf der Kommandozeile

Dieses plattformunabhängige Kommandozeilenprogramm ist vorrangig für die Auslösung von Alarmierungen in
*PersonalFME* (www.personalfme.de) entwickelt worden. Es kann jedoch auch als eigenständige Software genutzt werden.

**Dieses Programm funktioniert nur mit dem *neuen* Dienst von Groupalarm (www.groupalarm.com).** Groupalarm ist
ein kostenpflichtiger Dienst, für den ein separater Vertrag notwendig ist.

Das Programm besteht aus einer einzigen Datei: `trigger_groupalarm.py`

# Aufruf

**Voraussetzung ist eine funktionierende Installation von Python 3.6+**.

```commandline
python3 trigger_groupalarm.py [-h] [-t] [-c CONFIG_FILE] code time_point type
```

## Argumente
  |Argument|              Beschreibung|
  |--------|              ------------|
  |code|                  Die ausgelöste Alarmschleife (z.B. 09234)|
  |time_point|            Der Alarmzeitpunkt in beliebigem Format, z.B. "05.12.2021 19:51:52"|
  |type|                  Die Art der Alarmierung, beliebig (z.B. "Einsatzalarmierung" oder "Probealarm")|

## Optionale Argumente
  |Argument|            Beschreibung|
  |--------|            ------------|
  |-h, --help|          Die Hilfe anzeigen|
  |-t, --test|          Testet ob die Alarmkonfiguration korrekt ist und auf dem Groupalarm.com Server ausgelöst werden könnte - es wird kein tatsächlicher Alarm ausgelöst|
  |-c CONFIG_FILE, --config-file CONFIG_FILE| Alternativer Pfad für die YAML-Konfigurationsdatei, falls nicht angegeben muss die Konfigurationsdatei hier liegen: `config/config.yaml`|

## Beispiele

### Auslösung eines Alarms
```commandline
python3 trigger_groupalarm.py -c /home/<user>/config/config.yaml 09234 "05.12.2021 19:51:52" Einsatzalarmierung
```

### Testen einer Konfiguration

```commandline
python3 trigger_groupalarm.py -t -c /home/<user>/config/config.yaml 09234 "05.12.2021 19:51:52" Einsatzalarmierung
```

Wenn die Konfiguration ungültig ist, wird eine entsprechende Fehlermeldung ausgegeben. Dieser Befehl testet auch auf
dem Server von Groupalarm, ob der Alarm tatsächlich ausgelöst werden könnte.

**Hinweis:** Je nach Python-Installation kann das Kommando auch `python` sein (vor allem unter Windows).


# Konfiguration

Die Konfiguration erfolgt über eine YAML-Datei. Das notwendige Format ist:

```yaml
login:
  organization-id: 12345
  api-token: abcdefgh

alarms:
  "09234":
    resources:
      # nur EINE der folgenden Möglichkeiten:
      labels:
        - Kraftfahrer: 1
        - CBRN: 1
      scenarios:
        - SEG-Alarm
      units:
        - B
        - Bel
    # nur EINE der folgenden zwei Möglichkeiten:
    message: Einsatz für die SEG
    messageTemplate: SEG-Alarm

    # optional:
    closeEventInHours: 2
  "12345":
    resources:
      # Konfiguration für eine weitere Alarmschleife ...
```

Alternativ können die Login-Informationen in Umgebungsvariablen gespeichert werden:
* `ORGANIZATION_ID`
* `API_TOKEN`

## Erläuterungen

### Login

Hier werden die erforderlichen Informationen aus Ihrem Konto bei www.groupalarm.com eingetragen. Loggen Sie sich dort
ein, um die nötigen Informationen festzustellen:

* Unter *Organisation* -> *...* -> *Einstellungen* finden Sie Ihre Organisations-ID.
* Unter *Admin* -> *Berechtigungen* -> *API-Schlüssel* können Sie Ihren API-Schlüssel erzeugen, dieser funktioniert
  wie ein Passwort und sollte entsprechend behandelt werden. **Jeder kann mit diesem Schlüssel Alarmierungen auslösen.**
  Geben Sie dem API-Schlüssel einen sinnvollen Namen wie z.B. `PersonalFME`.


### Alarmschleifen

Für jede Alarmschleife muss eine separate Groupalarm-Konfiguration angegeben werden. Diese wird später durch die
Angabe der entsprechenden Schleife als Kommandozeilenparameter ausgelöst.


### Alarm-Ressourcen

Es können **entweder** Labels, Szenarien oder Einheiten alarmiert werden. Diese können nicht gemischt werden.
Im Falle von Labels wird für jede Position die gewünschte Anzahl festgelegt.
In allen Fällen erfolgt die Angabe über den in Groupalarm.com definierten *Namen* der Ressource. **Dieser sollte keine
Umlaute oder Sonderzeichen enthalten, um Problemen mit dem Encoding der YAML-Datei vorzubeugen**.
Konfigurieren Sie Groupalarm so, wie Sie das benötigen.

### Alarmnachricht

Als Alarmnachricht kann entweder ein individueller Text oder eine *Alarmvorlage* benutzt werden.

### Groupalarm-Ereignis

Jede Alarmierung erzeugt ein neues *Ereignis* in Groupalarm und dieses kann automatisch geschlossen werden, wenn
`closeEventInHours` angegeben wird. Andernfalls wird das *Ereignis* nicht automatisch geschlossen.

# Einbindung in PersonalFME

Die Einbindung der Alarmierungen in PersonalFME erfolgt als **externes Programm**. Unter Windows (mit Anaconda)
könnte das so aussehen:

```xml
<?xml version="1.0" encoding="UTF-8"?>

<config	xmlns="http://www.personalfme.de/v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.personalfme.de/v1 
        C:/Users\Benutzer\AppData\Roaming\PersonalFME\schema\config.xsd">

     <logins>
        <external/>
    </logins>

    <alarms>
        <code call="09234">
            <default>
                <alarms>
                    <external>
                        <command>call "C:\Users\<User>\Anaconda3\condabin\conda.bat" run "C:\Users\<User>\Anaconda3\python.exe" "C:\Users\<User>\Documents\code\personalfme-groupalarm2\src\trigger_groupalarm.py"</command>
                        <arguments>$CODE "$TIME" $TYPE</arguments>
                    </external>
                </alarms>
            </default>
        </code>
        <!-- Weitere Alarmierungen anderer Art ... -->
    </alarms>

</config>
```

Unter Linux unterscheidet sich der Aufruf von Python und könnte so aussehen:

```xml
<external>
    <command>python3 /opt/personalfme-groupalarm2/src/trigger_groupalarm.py</command>
    <arguments>$CODE "$TIME" $TYPE</arguments>
</external>
```

Die entsprechenden Pfade müssen natürlich an die entsprechende Situation auf dem Computer angepasst werden.

Für weitere Details wird auf das Handbuch von PersonalFME verwiesen: http://personalfme.de/handbuch.html



# Python-Umgebung

Das Programm benötigt eine funktionierende Installation von Python 3.6+. Dafür gibt es verschiedene Möglichkeiten
auf den unterschiedlichen Betriebssystemen. Empfehlenswert sind:

* Windows: Anaconda Individual Edition, https://www.anaconda.com/products/individual
* Linux: Python 3 aus dem Paketmanager des Betriebssystem (auf modernen Systemen meist schon vorhanden), unter
  Debian / Raspberry Pi OS z.B. installierbar mit:

```commandline
apt install python3
apt install python3-pip
```

Je nach installiertem Python müssen `python` oder `python3` bzw. `pip` oder `pip3` benutzt werden. `python` kann
auf älteren System jedoch auch auf Python 2 zeigen, welches nicht benutzt werden kann!

Die nötigen Abhängigkeiten können auf allen Plattformen mit mittels `pip` / `pip3` installiert werden:

```commandline
pip3 install -r requirements.txt
```

Benutzen Sie dafür im Falle von Windows und Anaconda die *Anaconda-Kommandozeile*, um die **richtige Anaconda-Umgebung**
anzuwenden.

Sie können auf der Kommandozeile testen, ob Python funktioniert:
```commandline
python3 -v
```

Im Falle von Anaconda muss vor jeder Benutzung von `python` die *Umgebung aktiviert werden*. Oben wird ein Beispiel
gezeigt, wie das unter Windows direkt aus *PersonalFME* heraus funktioniert.

# Lizenz

**personalfme-groupalarm2 - Trigger alarms via groupalarm.com on the command line**
 
 **Copyright (C) 2021 Ralf Rettig (info@personalfme.de)**

 This program is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as
 published by the Free Software Foundation, either version 3 of the
 License, or (at your option) any later version.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with this program.  If not, see <https://www.gnu.org/licenses/>.