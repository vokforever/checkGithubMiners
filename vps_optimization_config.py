# Конфигурация оптимизации для слабого VPS сервера
# Этот файл содержит настройки для снижения нагрузки на сервер

import os
from typing import Dict, Any

# --- ОСНОВНЫЕ НАСТРОЙКИ ОПТИМИЗАЦИИ ---

# Интервалы проверки (в минутах)
CHECK_INTERVALS = {
    'ultra_low_power': {
        'min_interval': 60,      # 1 час
        'max_interval': 4320,    # 3 дня
        'default_interval': 1440 # 1 день
    },
    'low_power': {
        'min_interval': 30,      # 30 минут
        'max_interval': 2880,    # 2 дня
        'default_interval': 720  # 12 часов
    },
    'medium_power': {
        'min_interval': 15,      # 15 минут
        'max_interval': 1440,    # 1 день
        'default_interval': 360  # 6 часов
    }
}

# Настройки для разных типов VPS
VPS_PROFILES = {
    'ultra_low_power': {
        'max_concurrent_requests': 1,
        'request_timeout': 30,
        'batch_size': 2,
        'memory_threshold_mb': 50,
        'log_level': 'WARNING',
        'cache_ttl_hours': 6,
        'enable_telegram_notifications': False,
        'enable_file_logging': False
    },
    'low_power': {
        'max_concurrent_requests': 2,
        'request_timeout': 25,
        'batch_size': 3,
        'memory_threshold_mb': 75,
        'log_level': 'INFO',
        'cache_ttl_hours': 4,
        'enable_telegram_notifications': True,
        'enable_file_logging': True
    },
    'medium_power': {
        'max_concurrent_requests': 3,
        'request_timeout': 20,
        'batch_size': 5,
        'memory_threshold_mb': 100,
        'log_level': 'INFO',
        'cache_ttl_hours': 2,
        'enable_telegram_notifications': True,
        'enable_file_logging': True
    }
}

# --- АДАПТИВНЫЕ НАСТРОЙКИ ---

class AdaptiveConfig:
    """Адаптивная конфигурация на основе нагрузки сервера"""
    
    def __init__(self, profile: str = 'low_power'):
        self.profile = profile
        self.current_load = 'normal'
        self.load_history = []
        self.max_history_size = 10
        
    def get_current_config(self) -> Dict[str, Any]:
        """Возвращает текущую конфигурацию на основе профиля и нагрузки"""
        base_config = VPS_PROFILES[self.profile].copy()
        
        # Адаптируем настройки на основе текущей нагрузки
        if self.current_load == 'high':
            base_config['max_concurrent_requests'] = max(1, base_config['max_concurrent_requests'] - 1)
            base_config['batch_size'] = max(1, base_config['batch_size'] - 1)
            base_config['request_timeout'] = min(60, base_config['request_timeout'] + 10)
        elif self.current_load == 'very_high':
            base_config['max_concurrent_requests'] = 1
            base_config['batch_size'] = 1
            base_config['request_timeout'] = 60
            base_config['enable_telegram_notifications'] = False
        
        return base_config
    
    def update_load(self, cpu_percent: float, memory_percent: float):
        """Обновляет оценку нагрузки сервера"""
        # Простая оценка нагрузки
        load_score = (cpu_percent + memory_percent) / 2
        
        if load_score > 80:
            new_load = 'very_high'
        elif load_score > 60:
            new_load = 'high'
        elif load_score > 40:
            new_load = 'normal'
        else:
            new_load = 'low'
        
        self.load_history.append(new_load)
        if len(self.load_history) > self.max_history_size:
            self.load_history.pop(0)
        
        # Определяем преобладающую нагрузку
        load_counts = {}
        for load in self.load_history:
            load_counts[load] = load_counts.get(load, 0) + 1
        
        self.current_load = max(load_counts.items(), key=lambda x: x[1])[0]
        
        return self.current_load

# --- НАСТРОЙКИ КЭШИРОВАНИЯ ---

CACHE_CONFIG = {
    'max_size_mb': 10,           # Максимальный размер кэша в МБ
    'cleanup_interval_hours': 4, # Интервал очистки кэша
    'compression_enabled': True,  # Сжатие кэша
    'persistent_storage': True,   # Сохранение кэша на диск
    'memory_only_fallback': True # Fallback на память если диск недоступен
}

# --- НАСТРОЙКИ ЛОГИРОВАНИЯ ---

LOGGING_CONFIG = {
    'max_file_size_mb': 5,       # Максимальный размер лог-файла
    'max_files_count': 3,        # Максимальное количество лог-файлов
    'log_rotation': 'daily',     # Ротация логов: daily, weekly, monthly
    'compress_old_logs': True,   # Сжатие старых логов
    'log_level_console': 'WARNING', # Уровень логирования в консоль
    'log_level_file': 'INFO'     # Уровень логирования в файл
}

# --- НАСТРОЙКИ HTTP КЛИЕНТА ---

HTTP_CONFIG = {
    'connection_pool_size': 10,   # Размер пула соединений
    'keepalive_timeout': 30,     # Таймаут keep-alive
    'max_redirects': 3,          # Максимальное количество редиректов
    'enable_compression': True,   # Включение сжатия
    'user_agent': 'GitHub-Release-Monitor-Bot-VPS-Optimized'
}

# --- НАСТРОЙКИ ПЛАНИРОВЩИКА ---

SCHEDULER_CONFIG = {
    'max_instances_per_job': 1,  # Максимум экземпляров одной задачи
    'coalesce_jobs': True,       # Объединение пропущенных задач
    'misfire_grace_time': 300,   # Время "прощения" пропущенных задач (сек)
    'job_defaults': {
        'coalesce': True,
        'max_instances': 1
    }
}

# --- ФУНКЦИИ ОПТИМИЗАЦИИ ---

def get_optimized_config(vps_type: str = 'low_power') -> Dict[str, Any]:
    """Возвращает оптимизированную конфигурацию для указанного типа VPS"""
    
    if vps_type not in VPS_PROFILES:
        vps_type = 'low_power'
    
    config = {
        'vps_profile': vps_type,
        'intervals': CHECK_INTERVALS[vps_type],
        'vps_settings': VPS_PROFILES[vps_type],
        'cache': CACHE_CONFIG,
        'logging': LOGGING_CONFIG,
        'http': HTTP_CONFIG,
        'scheduler': SCHEDULER_CONFIG
    }
    
    return config

def create_environment_file(config: Dict[str, Any], filename: str = '.env.optimized'):
    """Создает файл .env с оптимизированными настройками"""
    
    env_content = f"""# Оптимизированные настройки для слабого VPS
# Профиль: {config['vps_profile']}

# Основные настройки
VPS_PROFILE={config['vps_profile']}
MAX_CONCURRENT_REQUESTS={config['vps_settings']['max_concurrent_requests']}
REQUEST_TIMEOUT={config['vps_settings']['request_timeout']}
BATCH_SIZE={config['vps_settings']['batch_size']}

# Интервалы проверки (в минутах)
MIN_CHECK_INTERVAL={config['intervals']['min_interval']}
MAX_CHECK_INTERVAL={config['intervals']['max_interval']}
DEFAULT_CHECK_INTERVAL={config['intervals']['default_interval']}

# Кэширование
CACHE_TTL_HOURS={config['vps_settings']['cache_ttl_hours']}
CACHE_MAX_SIZE_MB={config['cache']['max_size_mb']}

# Логирование
LOG_LEVEL={config['vps_settings']['log_level']}
ENABLE_FILE_LOGGING={str(config['vps_settings']['enable_file_logging']).lower()}

# Уведомления
ENABLE_TELEGRAM_NOTIFICATIONS={str(config['vps_settings']['enable_telegram_notifications']).lower()}

# Управление ресурсами
MEMORY_THRESHOLD_MB={config['vps_settings']['memory_threshold_mb']}
"""
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(env_content)
        print(f"✅ Файл {filename} создан с оптимизированными настройками")
        return True
    except Exception as e:
        print(f"❌ Ошибка создания файла {filename}: {e}")
        return False

def get_system_recommendations() -> Dict[str, str]:
    """Возвращает рекомендации по оптимизации системы"""
    
    recommendations = {
        'system': [
            "Используйте swap-файл для увеличения виртуальной памяти",
            "Отключите ненужные службы и демоны",
            "Используйте lightweight дистрибутив Linux (Alpine, Debian minimal)",
            "Настройте автоматическую очистку логов"
        ],
        'python': [
            "Используйте Python 3.9+ для лучшей производительности",
            "Установите psutil для мониторинга ресурсов",
            "Используйте uvloop вместо asyncio для Linux",
            "Включите оптимизации Python (-O флаг)"
        ],
        'database': [
            "Используйте SQLite вместо PostgreSQL для простых случаев",
            "Включите WAL режим для SQLite",
            "Регулярно выполняйте VACUUM для SQLite",
            "Используйте индексы для часто запрашиваемых полей"
        ],
        'monitoring': [
            "Настройте мониторинг CPU и RAM",
            "Используйте htop или glances для мониторинга",
            "Настройте алерты при высокой нагрузке",
            "Ведите логи производительности"
        ]
    }
    
    return recommendations

# --- ТОЧКА ВХОДА ---

if __name__ == "__main__":
    print("🔧 Генератор оптимизированной конфигурации для VPS")
    print("=" * 50)
    
    # Создаем конфигурации для разных типов VPS
    for vps_type in ['ultra_low_power', 'low_power', 'medium_power']:
        config = get_optimized_config(vps_type)
        filename = f'.env.{vps_type}'
        create_environment_file(config, filename)
    
    # Выводим рекомендации
    print("\n📋 РЕКОМЕНДАЦИИ ПО ОПТИМИЗАЦИИ:")
    recommendations = get_system_recommendations()
    
    for category, items in recommendations.items():
        print(f"\n🔹 {category.upper()}:")
        for item in items:
            print(f"  • {item}")
    
    print("\n✅ Конфигурационные файлы созданы!")
    print("📁 Используйте .env.low_power для большинства случаев")
