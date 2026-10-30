from sqlalchemy import Column, Float, Integer, LargeBinary, REAL, String
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
    # Compressed cover image (webp when possible, jpeg as a fallback).
    album_art = Column(LargeBinary, nullable=True)
    rating = Column(REAL, nullable=True)
