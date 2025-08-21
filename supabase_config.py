import os
from typing import Dict, Any, List
from supabase import create_client, Client
from dotenv import load_dotenv
import logging
import json
from datetime import datetime, timezone

# Load environment variables
load_dotenv()

class SupabaseManager:
    def __init__(self):
        """Initialize Supabase connection"""
        self.supabase_url = os.getenv("SUPABASE_URL")
        # Пробуем сначала SUPABASE_KEY, затем SUPABASE_SERVICE_ROLE_KEY для совместимости
        self.supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY) must be set in .env file")
        
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        self.logger = logging.getLogger(__name__)
    
    def create_tables(self):
        """Create necessary tables if they don't exist"""
        try:
            # Create repository_priorities table
            self.client.rpc('create_repository_priorities_table').execute()
            self.logger.info("Repository priorities table created/verified")
        except Exception as e:
            self.logger.warning(f"Could not create table via RPC: {e}")
            # Fallback: try to create table directly via SQL
            self._create_table_directly()
    
    def _create_table_directly(self):
        """Create table directly using SQL"""
        try:
            sql = """
            CREATE TABLE IF NOT EXISTS checkgithub_repository_priorities (
                id SERIAL PRIMARY KEY,
                repo_name VARCHAR(255) UNIQUE NOT NULL,
                display_name VARCHAR(255) NOT NULL,
                update_count INTEGER DEFAULT 0,
                last_update TIMESTAMPTZ,
                check_interval INTEGER DEFAULT 1440,
                priority_score DECIMAL(5,3) DEFAULT 0.0,
                last_check TIMESTAMPTZ DEFAULT NOW(),
                consecutive_failures INTEGER DEFAULT 0,
                total_checks INTEGER DEFAULT 0,
                average_response_time DECIMAL(10,6) DEFAULT 0.0,
                priority_level VARCHAR(20) DEFAULT 'low',
                priority_color VARCHAR(10) DEFAULT '🟢',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_checkgithub_repo_name ON checkgithub_repository_priorities(repo_name);
            CREATE INDEX IF NOT EXISTS idx_checkgithub_priority_score ON checkgithub_repository_priorities(priority_score);
            CREATE INDEX IF NOT EXISTS idx_checkgithub_last_check ON checkgithub_repository_priorities(last_check);
            CREATE INDEX IF NOT EXISTS idx_checkgithub_priority_level ON checkgithub_repository_priorities(priority_level);
            """
            
            self.client.rpc('exec_sql', {'sql': sql}).execute()
            self.logger.info("Repository priorities table created directly")
        except Exception as e:
            self.logger.error(f"Failed to create table directly: {e}")
    
    def store_repository_priorities(self, priorities_data: Dict[str, Any]):
        """Store repository priorities data in Supabase"""
        try:
            priorities = priorities_data.get('priorities', {})
            repos_data = []
            
            for repo_name, repo_data in priorities.items():
                # Determine priority level based on score
                priority_level = self._get_priority_level(repo_data.get('priority_score', 0))
                
                repo_record = {
                    'repo_name': repo_name,
                    'display_name': repo_name.split('/')[-1],  # Extract repo name from owner/repo
                    'update_count': repo_data.get('update_count', 0),
                    'check_interval': repo_data.get('check_interval', 1440),
                    'priority_score': repo_data.get('priority_score', 0.0),
                    'last_check': repo_data.get('last_check'),
                    'consecutive_failures': repo_data.get('consecutive_failures', 0),
                    'total_checks': repo_data.get('total_checks', 0),
                    'average_response_time': repo_data.get('average_response_time', 0.0),
                    'priority_level': priority_level,
                    'priority_color': self._get_priority_color(repo_data.get('priority_score', 0)),
                    'updated_at': 'now()'
                }
                repos_data.append(repo_record)
            
            # Upsert data (insert or update)
            result = self.client.table('checkgithub_repository_priorities').upsert(
                repos_data,
                on_conflict='repo_name'
            ).execute()
            
            self.logger.info(f"Successfully stored {len(repos_data)} repository priorities in Supabase")
            return result
            
        except Exception as e:
            self.logger.error(f"Error storing repository priorities: {e}")
            raise
    
    def get_repository_priorities(self) -> List[Dict[str, Any]]:
        """Retrieve repository priorities from Supabase"""
        try:
            result = self.client.table('checkgithub_repository_priorities').select('*').execute()
            return result.data
        except Exception as e:
            self.logger.error(f"Error retrieving repository priorities: {e}")
            raise
    
    def get_priority_summary(self) -> Dict[str, Any]:
        """Get summary statistics of repository priorities"""
        try:
            repos = self.get_repository_priorities()
            
            high_priority = len([r for r in repos if r['priority_score'] >= 0.5])
            medium_priority = len([r for r in repos if 0.1 < r['priority_score'] < 0.5])
            low_priority = len([r for r in repos if r['priority_score'] <= 0.1])
            
            return {
                'total_repos': len(repos),
                'high_priority': high_priority,
                'medium_priority': medium_priority,
                'low_priority': low_priority,
                'last_updated': max([r['updated_at'] for r in repos]) if repos else None
            }
        except Exception as e:
            self.logger.error(f"Error calculating summary: {e}")
            return {}
    
    def update_repository_priority(self, repo_name: str, **kwargs):
        """Update specific repository priority data"""
        try:
            # Update priority level and color if score changed
            if 'priority_score' in kwargs:
                kwargs['priority_level'] = self._get_priority_level(kwargs['priority_score'])
                kwargs['priority_color'] = self._get_priority_color(kwargs['priority_score'])
            
            kwargs['updated_at'] = 'now()'
            
            result = self.client.table('checkgithub_repository_priorities').update(kwargs).eq('repo_name', repo_name).execute()
            
            if not result.data:
                raise ValueError(f"Repository {repo_name} not found")
            
            self.logger.info(f"Updated repository {repo_name}")
            return result.data[0]
            
        except Exception as e:
            self.logger.error(f"Error updating repository {repo_name}: {e}")
            raise
    
    def log_repository_check(self, repo_name: str, check_result: str, **kwargs):
        """Log a repository check result"""
        try:
            log_data = {
                'repo_name': repo_name,
                'check_result': check_result,
                'check_timestamp': 'now()',
                'response_time_ms': kwargs.get('response_time_ms'),
                'error_message': kwargs.get('error_message'),
                'update_detected': kwargs.get('update_detected', False),
                'new_release_tag': kwargs.get('new_release_tag'),
                'new_release_url': kwargs.get('new_release_url')
            }
            
            result = self.client.table('checkgithub_check_logs').insert(log_data).execute()
            self.logger.info(f"Logged check result for {repo_name}: {check_result}")
            return result.data[0] if result.data else None
            
        except Exception as e:
            self.logger.error(f"Error logging check result for {repo_name}: {e}")
            raise
    
    def get_telegram_report(self) -> str:
        """Generate Telegram format report from Supabase data"""
        try:
            repos = self.get_repository_priorities()
            
            # Sort by priority score
            repos.sort(key=lambda x: x['priority_score'], reverse=True)
            
            report_lines = ["📊 Приоритеты репозиториев:"]
            
            for repo in repos:
                priority_text = self._get_priority_text(repo['priority_score'])
                report_lines.append(
                    f"{repo['priority_color']} {repo['display_name']}\n"
                    f"   └ {priority_text} ({repo['priority_score']})\n"
                    f"   └ Интервал: {repo['check_interval']} мин\n"
                    f"   └ Обновлений: {repo['update_count']}, проверок: {repo['total_checks']}"
                )
            
            # Add legend
            report_lines.extend([
                "",
                "📝 Легенда:",
                "🔴 Высокий приоритет (≥0.5) — проверка каждые 15 мин",
                "🟡 Средний приоритет — проверка по расписанию",
                "🟢 Низкий приоритет (≤0.1) — проверка каждые 24 ч"
            ])
            
            # Check for connection issues
            issues = self._get_connection_issues()
            if issues:
                report_lines.extend(["", "⚠️ Проблемы с подключением"])
            
            return "\n".join(report_lines)
            
        except Exception as e:
            self.logger.error(f"Error generating Telegram report: {e}")
            return "❌ Ошибка при генерации отчета"
    
    def _get_connection_issues(self) -> List[Dict[str, Any]]:
        """Get repositories with connection issues"""
        try:
            repos = self.get_repository_priorities()
            return [r for r in repos if r.get('consecutive_failures', 0) > 0]
        except Exception as e:
            self.logger.error(f"Error getting connection issues: {e}")
            return []
    
    def _get_priority_level(self, score: float) -> str:
        """Determine priority level based on score"""
        if score >= 0.5:
            return 'high'
        elif score > 0.1:
            return 'medium'
        else:
            return 'low'
    
    def _get_priority_color(self, score: float) -> str:
        """Get priority color emoji"""
        if score >= 0.5:
            return '🔴'
        elif score > 0.1:
            return '🟡'
        else:
            return '🟢'
    
    def _get_priority_text(self, score: float) -> str:
        """Get priority text in Russian"""
        if score >= 0.5:
            return 'Высокий приоритет'
        elif score > 0.1:
            return 'Средний приоритет'
        else:
            return 'Низкий приоритет'
    
    def migrate_from_json(self, json_file_path: str = "repo_priority.json"):
        """Migrate data from existing JSON file to Supabase"""
        try:
            if not os.path.exists(json_file_path):
                self.logger.warning(f"JSON file {json_file_path} not found")
                return False
            
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Store data in Supabase
            self.store_repository_priorities(data)
            
            # Create backup of JSON file
            backup_path = f"{json_file_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.rename(json_file_path, backup_path)
            
            self.logger.info(f"Successfully migrated data from {json_file_path} to Supabase")
            self.logger.info(f"Original file backed up to {backup_path}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error migrating from JSON: {e}")
            raise
    
    def export_to_json(self, file_path: str = None) -> str:
        """Export current Supabase data to JSON format"""
        try:
            repos = self.get_repository_priorities()
            
            export_data = {
                "priorities": {},
                "last_update": datetime.now(timezone.utc).isoformat(),
                "version": "3.0",
                "repos_count": len(repos),
                "source": "supabase"
            }
            
            for repo in repos:
                export_data["priorities"][repo['repo_name']] = {
                    "update_count": repo['update_count'],
                    "last_update": repo['last_update'],
                    "check_interval": repo['check_interval'],
                    "priority_score": repo['priority_score'],
                    "last_check": repo['last_check'],
                    "consecutive_failures": repo['consecutive_failures'],
                    "total_checks": repo['total_checks'],
                    "average_response_time": repo['average_response_time']
                }
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
                self.logger.info(f"Data exported to {file_path}")
            
            return json.dumps(export_data, indent=2, ensure_ascii=False, default=str)
            
        except Exception as e:
            self.logger.error(f"Error exporting to JSON: {e}")
            raise
    
    def close(self):
        """Close Supabase connection"""
        if hasattr(self, 'client'):
            try:
                self.client.auth.sign_out()
            except:
                pass

# Convenience functions for easy integration
def get_telegram_report() -> str:
    """Get Telegram format report"""
    supabase = SupabaseManager()
    try:
        return supabase.get_telegram_report()
    finally:
        supabase.close()

def update_repository_data(repo_name: str, **kwargs):
    """Update repository data"""
    supabase = SupabaseManager()
    try:
        return supabase.update_repository_priority(repo_name, **kwargs)
    finally:
        supabase.close()

def log_check(repo_name: str, result: str, **kwargs):
    """Log a check result"""
    supabase = SupabaseManager()
    try:
        return supabase.log_repository_check(repo_name, result, **kwargs)
    finally:
        supabase.close()
