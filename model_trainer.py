from sklearn.ensemble import RandomForestRegressor
import numpy as np
import pandas as pd
import joblib
from datetime import datetime

def generate_synthetic_user_data(n_samples):
    """
    Generate synthetic user interaction data with features that might predict engagement
    Features:
    - avg_session_duration: Average time spent per session (minutes)
    - visits_per_week: Number of visits per week
    - response_rate: How often they respond to notifications (%)
    - feature_usage_depth: How many different features they use (count)
    Target:
    - engagement_score: Overall user engagement (0-100)
    """
    np.random.seed(int(datetime.now().timestamp()))
    
    data = {
        'avg_session_duration': np.clip(np.random.normal(15, 8, n_samples), 1, 60),
        'visits_per_week': np.clip(np.random.normal(5, 2, n_samples), 1, 14),
        'response_rate': np.clip(np.random.normal(70, 15, n_samples), 0, 100),
        'feature_usage_depth': np.clip(np.random.normal(6, 2, n_samples), 1, 10)
    }
    
    df = pd.DataFrame(data)
    
    # Create engagement score with some realistic relationships
    engagement_score = (
        0.3 * df['avg_session_duration'] / df['avg_session_duration'].max() * 100 +
        0.3 * df['visits_per_week'] / df['visits_per_week'].max() * 100 +
        0.2 * df['response_rate'] +
        0.2 * df['feature_usage_depth'] / df['feature_usage_depth'].max() * 100
    )
    
    df['engagement_score'] = engagement_score
    return df

def train_model():
    try:
        print(f"[{datetime.now()}] Starting model training")
        
        # Generate training data of 250 random samples
        df = generate_synthetic_user_data(n_samples=250)
        
        # Prepare features and target
        X = df.drop('engagement_score', axis=1)
        y = df['engagement_score']
        
        # TODO: Train model to predict Y given X
        # you can use any model but we suggest (and import) RandomForestRegressor
        model = ...
        
        # Save model and metadata
        model_info = {
            'model': model,
            'feature_names': list(X.columns),
            'training_time': datetime.now().isoformat()
        }
        
        joblib.dump(model_info, '/shared-volume/model.joblib')
        
        print(f"[{datetime.now()}] Model trained and saved")
            
        return True
        
    except Exception as e:
        print(f"[{datetime.now()}] Error during training: {e}")
        return False

if __name__ == '__main__':
    train_model()