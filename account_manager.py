import json
import os
import random
from pathlib import Path
from datetime import datetime, timedelta

class AccountManager:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path.home() / '.clipforge' / 'accounts.json'
        self.config_path = config_path
        self.accounts = self._load_accounts()
        self.current_account = None
        self.proxies = {}
    
    def _load_accounts(self):
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('accounts', [])
        return []
    
    def _save_accounts(self):
        os.makedirs(self.config_path.parent, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump({'accounts': self.accounts}, f, indent=2, ensure_ascii=False)
    
    def add_account(self, name, client_secrets_path, credentials_path=None, proxy=None, description=''):
        """Добавляет новый аккаунт YouTube"""
        account = {
            'id': f'account_{len(self.accounts)}',
            'name': name,
            'client_secrets': client_secrets_path,
            'credentials': credentials_path,
            'proxy': proxy,
            'description': description,
            'added_at': datetime.now().isoformat(),
            'last_used': None,
            'upload_count': 0,
            'active': True
        }
        
        self.accounts.append(account)
        self._save_accounts()
        
        if proxy:
            self.proxies[account['id']] = proxy
        
        return account['id']
    
    def remove_account(self, account_id):
        """Удаляет аккаунт"""
        self.accounts = [a for a in self.accounts if a['id'] != account_id]
        self._save_accounts()
        
        if account_id in self.proxies:
            del self.proxies[account_id]
    
    def get_account(self, account_id=None):
        """Получает аккаунт по ID или текущий"""
        if account_id:
            return next((a for a in self.accounts if a['id'] == account_id), None)
        return self.current_account
    
    def set_current_account(self, account_id):
        """Устанавливает текущий аккаунт"""
        account = self.get_account(account_id)
        if account:
            self.current_account = account
            account['last_used'] = datetime.now().isoformat()
            self._save_accounts()
        return account
    
    def get_all_accounts(self):
        """Возвращает все аккаунты"""
        return self.accounts
    
    def get_active_accounts(self):
        """Возвращает только активные аккаунты"""
        return [a for a in self.accounts if a.get('active', True)]
    
    def rotate_account(self):
        """Ротирует аккаунт (выбирает следующий)"""
        active = self.get_active_accounts()
        if not active:
            return None
        
        if self.current_account:
            current_index = next((i for i, a in enumerate(active) if a['id'] == self.current_account['id']), -1)
            next_index = (current_index + 1) % len(active)
        else:
            next_index = 0
        
        next_account = active[next_index]
        self.set_current_account(next_account['id'])
        return next_account
    
    def get_random_account(self):
        """Выбирает случайный аккаунт"""
        active = self.get_active_accounts()
        if not active:
            return None
        
        account = random.choice(active)
        self.set_current_account(account['id'])
        return account
    
    def get_proxy_for_account(self, account_id=None):
        """Получает прокси для аккаунта"""
        if account_id is None and self.current_account:
            account_id = self.current_account['id']
        
        return self.proxies.get(account_id)
    
    def set_proxy(self, account_id, proxy):
        """Устанавливает прокси для аккаунта"""
        account = self.get_account(account_id)
        if account:
            account['proxy'] = proxy
            self.proxies[account_id] = proxy
            self._save_accounts()
    
    def increment_upload_count(self, account_id=None):
        """Увеличивает счетчик загрузок"""
        if account_id is None and self.current_account:
            account_id = self.current_account['id']
        
        account = self.get_account(account_id)
        if account:
            account['upload_count'] = account.get('upload_count', 0) + 1
            self._save_accounts()
    
    def get_account_stats(self):
        """Возвращает статистику по аккаунтам"""
        return {
            'total': len(self.accounts),
            'active': len(self.get_active_accounts()),
            'current': self.current_account['name'] if self.current_account else None,
            'accounts': [
                {
                    'id': a['id'],
                    'name': a['name'],
                    'upload_count': a.get('upload_count', 0),
                    'last_used': a.get('last_used'),
                    'proxy': a.get('proxy'),
                    'active': a.get('active', True)
                }
                for a in self.accounts
            ]
        }
    
    def toggle_account(self, account_id):
        """Включает/выключает аккаунт"""
        account = self.get_account(account_id)
        if account:
            account['active'] = not account.get('active', True)
            self._save_accounts()
        return account

# Глобальный экземпляр
account_manager = AccountManager()

def add_account(name, client_secrets_path, credentials_path=None, proxy=None, description=''):
    return account_manager.add_account(name, client_secrets_path, credentials_path, proxy, description)

def remove_account(account_id):
    account_manager.remove_account(account_id)

def get_account(account_id=None):
    return account_manager.get_account(account_id)

def set_current_account(account_id):
    return account_manager.set_current_account(account_id)

def get_all_accounts():
    return account_manager.get_all_accounts()

def rotate_account():
    return account_manager.rotate_account()

def get_random_account():
    return account_manager.get_random_account()

def get_proxy(account_id=None):
    return account_manager.get_proxy_for_account(account_id)

def set_proxy(account_id, proxy):
    account_manager.set_proxy(account_id, proxy)

def get_account_stats():
    return account_manager.get_account_stats()

def toggle_account(account_id):
    return account_manager.toggle_account(account_id)