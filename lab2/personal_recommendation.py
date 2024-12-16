# -*- coding: utf-8 -*-
"""Копия блокнота "PYАД ЛР2.ipynb"

Automatically generated by Colab.
"""

import pandas as pd
import pickle
from surprise import Dataset, Reader, SVD, accuracy
from surprise.model_selection import train_test_split as surprise_train_test_split, GridSearchCV
from sklearn.linear_model import SGDRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

ratings = pd.read_csv("Ratings.csv")
books = pd.read_csv("Books.csv")

ratings_copy = ratings.copy()

"""## Обработка данных"""

# Удалим столбцы с изображениями (они не нужны)
books = books.drop(columns=['Image-URL-S', 'Image-URL-M', 'Image-URL-L'])

# Исправим строчки со сдвигами
missing_rows = books[books["Year-Of-Publication"].map(str).str.match("[^0-9]")]
for index, row in missing_rows.iterrows():
      parts = row['Book-Title'].split(';')
      books.at[index, 'Publisher'] = row['Year-Of-Publication']
      books.at[index, 'Year-Of-Publication'] = row['Book-Author']
      if len(parts) > 1:  # Если нашли смещение
        books.at[index, 'Book-Author'] = parts[-1]
      else:
        books.at[index, 'Book-Author'] = None

# Исправление некорректных лет публикации
current_year = pd.Timestamp.now().year
books['Year-Of-Publication'] = pd.to_numeric(books['Year-Of-Publication'], errors='coerce')
books.loc[(books['Year-Of-Publication'] > current_year) | (books['Year-Of-Publication'] < 0), 'Year-Of-Publication'] = 2024

# Замена пропусков на "Неизвестно"
books['Book-Author'] = books['Book-Author'].fillna('Unknown')
books['Publisher'] = books['Publisher'].fillna('Unknown')

# Проверка обновленных данных
print(books.info())

# Исключение записей с рейтингом 0
ratings_copy = ratings_copy[ratings_copy['Book-Rating'] > 0]

# Убираем книги с единственным рейтингом
book_counts = ratings_copy['ISBN'].value_counts()
valid_books = book_counts[book_counts > 1].index
ratings_copy = ratings_copy[ratings_copy['ISBN'].isin(valid_books)]

# Убираем пользователей, оценивших только одну книгу
user_counts = ratings_copy['User-ID'].value_counts()
valid_users = user_counts[user_counts > 1].index
ratings_copy = ratings_copy[ratings_copy['User-ID'].isin(valid_users)]

# Проверка обновленных данных
print(ratings_copy.info())

"""## Обучение SVD"""

reader = Reader(rating_scale=(1, 10))
svd_data = Dataset.load_from_df(ratings_copy[['User-ID', 'ISBN', 'Book-Rating']], reader)
train_set = svd_data.build_full_trainset()

# Подбор гиперпараметров SVD
param_grid = {
    'n_factors': [50, 100],
    'n_epochs': [20, 30],
    'lr_all': [0.005, 0.01],
    'reg_all': [0.02, 0.1]
}
gs = GridSearchCV(SVD, param_grid, measures=['mae'], cv=3)
gs.fit(svd_data)

# Выбор и обучение лучшей модели
svd = gs.best_estimator['mae']
svd.fit(train_set)

trains_set, test_set = surprise_train_test_split(svd_data, test_size=0.1)
predictions = svd.test(test_set)
mae_svd = accuracy.mae(predictions)
print(mae_svd)

# Сохранение модели SVD
with open('svd.pkl', 'wb') as f:
    pickle.dump(svd, f)

"""## Обучение SGD"""

# Объединение данных рейтингов и книг
merged_data = ratings_copy.merge(books, left_on='ISBN', right_on='ISBN')

# Векторизация названий книг
vectorizer = TfidfVectorizer(max_features=100)
vectorized_titles = vectorizer.fit_transform(merged_data['Book-Title']).toarray()

# Кодирование категориальных признаков (автор, издатель, год)
categorical_features = merged_data[['Book-Author', 'Publisher', 'Year-Of-Publication']]
categorical_encoded = pd.DataFrame({
    col: pd.factorize(categorical_features[col])[0]
    for col in categorical_features
})

# Объединение всех признаков
features = pd.concat(
    [categorical_encoded, pd.DataFrame(vectorized_titles)],
    axis=1
)
features.columns = features.columns.astype(str)

# Нормализуем значения
scaler = StandardScaler()
X = scaler.fit_transform(features)
y = merged_data['Book-Rating']

# Разделение данных на тренировочную и тестовую выборки
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=29)

# Обучение модели линейной регрессии
sgd = SGDRegressor(max_iter=1000, tol=1e-3)
sgd.fit(X_train, y_train)

# Тестирование модели
y_predict = sgd.predict(X_test)
mae_sgd = mean_absolute_error(y_test, y_predict)
print(mae_sgd)

# Сохранение модели линейной регрессии
with open('linreg.pkl', 'wb') as f:
    pickle.dump(sgd, f)

"""## Рекомендации"""

# Поиск пользователя с наибольшим количеством рейтингов "0"
user_with_most_zeros = ratings[ratings['Book-Rating'] == 0]['User-ID'].value_counts().idxmax()
zero_rated_books = ratings[(ratings['User-ID'] == user_with_most_zeros) & (ratings['Book-Rating'] == 0)]

# Предсказания для книг с рейтингом "0"
recommendations = []
for item_id in zero_rated_books['ISBN']:
    svd_pred = svd.predict(user_with_most_zeros, item_id).est
    if svd_pred >= 8:
        book_features = features[merged_data['ISBN'] == item_id].to_numpy()
        linreg_pred = sgd.predict(book_features)[0]
        recommendations.append((item_id, svd_pred, linreg_pred))

recommendations.sort(key=lambda x: x[2], reverse=True)

# Записываем рекомендации в user_recommendations.txt
with open("user_recommendations.txt", "w") as rec_file:
  for item_id, svd_pred, linreg_pred in recommendations:
    book_title = books.loc[books['ISBN'] == item_id, 'Book-Title'].values[0]
    rec_file.write(f"Book: {book_title}\nPredicted rating: {svd_pred:.2f}\nSGD rating: {linreg_pred:.2f}\n\n")
