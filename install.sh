#!/bin/bash
# RaporOku Agent — Mac/Linux Otomatik Kurulum
# curl -fsSL https://raporoku.com/static/downloads/install.sh | bash

set -e

APP_NAME="RaporOku Agent"
INSTALL_DIR="$HOME/.raporoku"
AGENT_URL="https://raporoku.com/static/downloads/raporoku-agent.py"

echo ""
echo "============================================"
echo "  $APP_NAME — Otomatik Kurulum"
echo "============================================"
echo ""

# 1. Python kontrolü
echo "[1/3] Python kontrol ediliyor..."
PYTHON=""
for cmd in python3 python; do
    if command -v $cmd &>/dev/null; then
        ver=$($cmd --version 2>&1)
        if echo "$ver" | grep -q "Python 3"; then
            PYTHON=$cmd
            echo "  ✓ $ver"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  ✗ Python 3 bulunamadı!"
    echo "  Mac: brew install python3"
    echo "  Linux: sudo apt install python3 python3-pip"
    exit 1
fi

# 2. Klasör + dosya
echo "[2/3] Dosyalar indiriliyor..."
mkdir -p "$INSTALL_DIR"
curl -fsSL "$AGENT_URL" -o "$INSTALL_DIR/agent.py"
echo "  ✓ Agent indirildi"

# 3. Bağımlılıklar
echo "[3/3] Bağımlılıklar kuruluyor..."
$PYTHON -m pip install --quiet pyserial requests 2>/dev/null || pip3 install --quiet pyserial requests
echo "  ✓ pyserial + requests"

# Çalıştırıcı script
cat > "$INSTALL_DIR/raporoku-agent" << SCRIPT
#!/bin/bash
cd "$INSTALL_DIR"
$PYTHON agent.py "\$@"
SCRIPT
chmod +x "$INSTALL_DIR/raporoku-agent"

# PATH'e ekle
if ! echo "$PATH" | grep -q "$INSTALL_DIR"; then
    echo "export PATH=\"\$PATH:$INSTALL_DIR\"" >> "$HOME/.bashrc" 2>/dev/null
    echo "export PATH=\"\$PATH:$INSTALL_DIR\"" >> "$HOME/.zshrc" 2>/dev/null
fi

echo ""
echo "============================================"
echo "  ✓ Kurulum tamamlandı!"
echo "============================================"
echo ""
echo "  İlk kurulum: raporoku-agent --setup"
echo "  Çalıştırma:  raporoku-agent"
echo "  Port listele: raporoku-agent --list-ports"
echo ""

read -p "Şimdi kurulum sihirbazını başlatmak ister misiniz? (E/H) " answer
if [ "$answer" = "E" ] || [ "$answer" = "e" ]; then
    $PYTHON "$INSTALL_DIR/agent.py" --setup
fi
