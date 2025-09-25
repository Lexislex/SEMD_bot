from typing import Optional

# Настройка логирования
import logging
logger = logging.getLogger(__name__)

def format_releaseNotes(relNotes: Optional[str]) -> str:
    """
    Форматирует примечания к выпуску.
    
    Args:
        relNotes: сырые примечания к выпуску
    
    Returns:
        str: отформатированные примечания
    """
    if relNotes is None:
        return "Нет информации об изменениях"
    
    try:
        # Очистка строки
        cleaned_notes = relNotes.replace('\n', '').strip()
        if not cleaned_notes or cleaned_notes == ';':
            return "Нет информации об изменениях"
        
        # Удаляем завершающую точку с запятой если есть
        if cleaned_notes.endswith(';'):
            cleaned_notes = cleaned_notes[:-1]
        
        data = {}
        
        # Обрабатываем каждый элемент отдельно
        for item in cleaned_notes.split(';'):
            item = item.strip()
            if not item:
                continue
                
            # Разделяем только если есть двоеточие
            if ':' in item:
                parts = item.split(':', 1)  # Разделяем только по первому двоеточию
                key = parts[0].strip()
                value = parts[1].strip() if len(parts) > 1 else ''
                
                # Добавляем только если значение не '0'
                if value != '0':
                    data[key] = value
            else:
                # Если нет двоеточия, добавляем как ключ с пустым значением
                data[item] = ''
    
    except Exception as e:
        # Деталь можно записать на DEBUG, чтобы не дублировать ошибок на верхнем уровне
        logger.debug("Ошибка обработки изменений: %s; raw=%r", e, relNotes)
        return "Нет информации об изменениях" 

    # Формируем результат
    if not data:
        return "Нет информации об изменениях"
    
    result_string = '\n'.join(
        f"{key}: {value}" if value else f"{key}" 
        for key, value in data.items()
    )
    return result_string

if __name__ == '__main__':
    logger.warning('This module is not for direct call')
    exit(1)