from sqlalchemy import Column, Float, Integer, REAL, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    poster_url = Column(String, nullable=True)
    # Path relative to the site folder, e.g. "images/movies/the-matrix-1999.jpg".
    poster_path = Column(String, nullable=True)
    year = Column(Integer, nullable=True)
    imdb_const = Column(String(32), nullable=True)
    imdb_rating = Column(Float, nullable=True)
    imdb_votes = Column(Integer, nullable=True)
    tomatoes_rating = Column(Integer, nullable=True)
    rating = Column(Integer, nullable=True)
    title_type = Column(String, nullable=True)
    genres = Column(String, nullable=True)
    directors = Column(String, nullable=True)


class Music(Base):
    __tablename__ = "music"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    album = Column(String, nullable=True)
    artist = Column(String, nullable=True)
    # Path relative to the site folder, e.g. "images/music/<hash>.webp".
    poster_path = Column(String, nullable=True)
    rating = Column(REAL, nullable=True)


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(32), nullable=False, unique=True, index=True)
    title = Column(String, nullable=False)
    poster_url = Column(String, nullable=True)
    poster_path = Column(String, nullable=True)
    rating = Column(Float, nullable=True)


class Anime(Base):
    __tablename__ = "anime"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mal_id = Column(Integer, nullable=False, unique=True, index=True)
    title = Column(String, nullable=False)
    title_type = Column(String, nullable=True)
    episodes = Column(Integer, nullable=True)
    poster_url = Column(String, nullable=True)
    poster_path = Column(String, nullable=True)
    rating = Column(Float, nullable=True)


class Manga(Base):
    __tablename__ = "manga"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mal_id = Column(Integer, nullable=False, unique=True, index=True)
    title = Column(String, nullable=False)
    title_type = Column(String, nullable=True)
    chapters = Column(Integer, nullable=True)
    volumes = Column(Integer, nullable=True)
    poster_url = Column(String, nullable=True)
    poster_path = Column(String, nullable=True)
    rating = Column(Float, nullable=True)
