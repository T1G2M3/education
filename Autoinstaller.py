# autoinstaller.py
import os
import sys
import shutil
import subprocess
from tqdm import tqdm
from colorama import Fore, Style, init

init(autoreset=True)

class AutoInstaller:
    def __init__(self):
        self.repo_url = "git@github.com:vas_username/BinanceBot.git"  # Použijte SSH URL
        self.project_dir = "BinanceBot"
        self.required_dirs = [
            'config',
            'core',
            'strategies',
            'ui',
            'ai',
            'tests',
            'logs'
        ]

    def print_header(self):
        print(Fore.CYAN + r"""
  ____  _                               _____      _   _            
 |  _ \(_)                             / ____|    | | | |           
 | |_) |_ _ __   __ _ _ __   ___ ___  | |    _   _| |_| |_ ___ _ __ 
 |  _ <| | '_ \ / _` | '_ \ / __/ _ \ | |   | | | | __| __/ _ \ '__|
 | |_) | | | | | (_| | | | | (_|  __/ | |___| |_| | |_| ||  __/ |   
 |____/|_|_| |_|\__,_|_| |_|\___\___|  \_____\__,_|\__|\__\___|_|   
                                                                    
                                                                                     
        """)
        print(Fore.YELLOW + "🚀 Automatický instalační systém pro Trading Bot\n")

    def check_git(self):
        try:
            subprocess.check_output(['git', '--version'])
            return True
        except Exception:
            print(Fore.RED + "❌ Git není nainstalován!")
            print(Fore.WHITE + "Nainstalujte git pomocí:")
            print(Fore.CYAN + "  sudo apt-get install git" + Fore.WHITE + " (Linux)")
            print(Fore.CYAN + "  brew install git" + Fore.WHITE + " (MacOS)")
            print(Fore.CYAN + "  https://git-scm.com/downloads" + Fore.WHITE + " (Windows)")
            sys.exit(1)

    def clone_repository(self):
        print(Fore.WHITE + "⬇️  Stahuji projekt z GitHubu...")
        try:
            subprocess.check_call(['git', 'clone', self.repo_url, self.project_dir])
            print(Fore.GREEN + "✓ Repozitář úspěšně stažen")
        except Exception as e:
            print(Fore.RED + f"❌ Chyba při stahování: {str(e)}")
            print(Fore.YELLOW + "Zkontrolujte:")
            print("- Připojení k internetu")
            print("- Přístupová práva k repozitáři")
            print("- Správnost SSH klíčů")
            sys.exit(1)

    def setup_environment(self):
        print(Fore.CYAN + "\n⚙️  Konfigurace prostředí...")
        
        # API klíče
        api_key = input(Fore.WHITE + "Zadejte Binance API klíč: ")
        api_secret = input(Fore.WHITE + "Zadejte Binance API secret: ")
        
        # Zápis do .env
        with open(f"{self.project_dir}/.env", "w") as f:
            f.write(f"BINANCE_API_KEY={api_key}\n")
            f.write(f"BINANCE_API_SECRET={api_secret}\n")
        
        print(Fore.GREEN + "✓ Konfigurační soubory vytvořeny")

    def install_dependencies(self):
        print(Fore.CYAN + "\n📦 Instalace závislostí...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "-r",
                f"{self.project_dir}/requirements.txt"
            ])
            print(Fore.GREEN + "✓ Závislosti úspěšně nainstalovány")
        except Exception as e:
            print(Fore.RED + f"❌ Chyba při instalaci: {str(e)}")
            sys.exit(1)

    def finalize(self):
        print(Fore.GREEN + "\n🎉 Instalace dokončena!")
        print(Fore.YELLOW + "\nDalší kroky:")
        print(Fore.WHITE + f"1. Upravte konfiguraci: {self.project_dir}/config/config.yaml")
        print(Fore.WHITE + f"2. Spusťte bot: cd {self.project_dir} && python -m core.main")
        print(Fore.WHITE + f"3. Dashboard: cd {self.project_dir} && python -m ui.web_app\n")

    def run(self):
        self.print_header()
        self.check_git()
        self.clone_repository()
        self.setup_environment()
        self.install_dependencies()
        self.finalize()

if __name__ == "__main__":
    try:
        installer = AutoInstaller()
        installer.run()
    except KeyboardInterrupt:
        print(Fore.RED + "\n❌ Instalace přerušena uživatelem!")
        sys.exit(1)
