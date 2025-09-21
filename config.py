import certifi

class Config:
    SECRET_KEY = "your-secret-key"  

    # Full MongoDB connection string
    MONGO_URI = (
        "mongodb+srv://srisha1045:Jungk0ok-7"
        "@cluster0.muqelad.mongodb.net/exam_portal"
        "?retryWrites=true&w=majority&appName=Cluster0"
    )

    # TLS for certificate validation
    MONGO_TLSCAFILE = certifi.where()
