from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

corpus = [
    'This is the first document.',
    'This document is the second document.',
]

vectorizer = TfidfVectorizer()
vectorizer.fit(corpus)

# The issue is that the 'copy' parameter is ignored in transform.
# Since transform on text always creates a new matrix, 
# 'copy' doesn't really affect the input.
# But let's see if we can trigger any unexpected behavior or if it's just a refactoring fix.

X = vectorizer.transform(corpus, copy=True)
print("Transform successful with copy=True")

X2 = vectorizer.transform(corpus, copy=False)
print("Transform successful with copy=False")
