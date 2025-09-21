import os

class Config:
    # Secret key for session security
    SECRET_KEY = os.environ.get('SECRET_KEY', 'this_should_be_changed')

    # MongoDB Atlas connection string (from env or default)
    MONGO_URI = os.environ.get(
        'MONGO_URI',
        'mongodb+srv://srisha1045:<Jungk0ok-7>@cluster0.muqelad.mongodb.net/essay_exam_db?retryWrites=true&w=majority&appName=Cluster0'
    )
