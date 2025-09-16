import logging
import sys
import litellm


def setup_logger(name, level=logging.INFO):
    """Function to setup a logger for Lambda with CloudWatch output"""
    logger = logging.getLogger(name)
    
    if logger.hasHandlers():
        logger.handlers.clear()
    
    logger.setLevel(level)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Use stdout for CloudWatch integration
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    logger.propagate = False
    
    return logger


def setup_litellm_logger():
    """Configure LiteLLM logging to prevent warning messages for CloudWatch"""
    litellm_logger = logging.getLogger('litellm')
    litellm_logger.setLevel(logging.WARNING)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    
    litellm_logger.addHandler(console_handler)
    litellm_logger.propagate = False


def get_logger(name):
    """Get a logger for Lambda use with CloudWatch integration"""
    setup_litellm_logger()
    
    # Simplified processor mapping for Lambda
    processor_mappings = {
        'lambda_node_processor': [
            'bs.parseHtmlForDescription',
            'bs.scrape', 
            'bs.generate_description', 
            'bs.createVectors',
            'bs.db',
            'bs.topCompany',
            'processor',
            'handler',
            'config',
            'utils'
        ]
    }
    
    base_name = name.split('.')[-1].replace('.py', '')
    
    target_processor = None
    for processor, related_modules in processor_mappings.items():
        if (base_name == processor or 
            any(name.startswith(module) for module in related_modules) or
            any(module in name for module in related_modules)):
            target_processor = processor
            break
    
    if not target_processor:
        temp_logger = logging.getLogger(name)
        if not temp_logger.hasHandlers():
            console_handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(formatter)
            console_handler.setLevel(logging.INFO) 
            temp_logger.addHandler(console_handler)
            temp_logger.propagate = False
        return temp_logger

    return setup_logger(name)