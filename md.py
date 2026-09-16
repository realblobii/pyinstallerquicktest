#!/usr/bin/python3

import os
import threading
import io
import requests
import musicbrainzngs
import concurrent.futures
from yt_dlp import YoutubeDL
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, error
from mutagen.mp3 import MP3

import customtkinter as ctk
from tkinter import messagebox
from PIL import Image

# Setup MusicBrainz user agent
musicbrainzngs.set_useragent("MusicBrowserGUI", "2.0", "realblobii [at] proton [dot] me")

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class DownloadProgressPopup(ctk.CTkToplevel):
    def __init__(self, parent, title="Downloading"):
        super().__init__(parent)
        self.geometry("450x180")
        self.title(title)
        self.resizable(False, False)
        self.grab_set()

        self.label = ctk.CTkLabel(self, text="Preparing parallel downloads...", font=("Helvetica", 13))
        self.label.pack(pady=20, padx=10)

        self.progress_bar = ctk.CTkProgressBar(self, width=380)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=10)

        self.stats_label = ctk.CTkLabel(self, text="0.0% Downloaded", font=("Helvetica", 11, "bold"))
        self.stats_label.pack(pady=5)

    def update_progress(self, percent, status_text):
        self.label.configure(text=status_text)
        self.progress_bar.set(percent / 100.0)
        self.stats_label.configure(text=f"{percent:.1f}% Downloaded")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("musicDL")
        self.geometry("950x720")

        self.search_mode = ctk.StringVar(value="album")
        
        self.setup_ui()

    def setup_ui(self):
        # Top Container for Spotlight UI
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=40, pady=(30, 10))

        # Radio Buttons for Mode Selection
        mode_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        mode_frame.pack(anchor="center", pady=(0, 10))
        
        rb_album = ctk.CTkRadioButton(mode_frame, text="Search Albums", variable=self.search_mode, value="album", font=("Helvetica", 14))
        rb_album.pack(side="left", padx=15)
        
        rb_song = ctk.CTkRadioButton(mode_frame, text="Search Songs", variable=self.search_mode, value="song", font=("Helvetica", 14))
        rb_song.pack(side="left", padx=15)

        # Main Search Bar Setup
        search_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        search_frame.pack(anchor="center", fill="x", expand=True)

        self.artist_entry = ctk.CTkEntry(search_frame, placeholder_text="Artist (Optional)", width=200, height=50, font=("Helvetica", 16))
        self.artist_entry.pack(side="left", padx=(0, 10))

        # Spotlight style large entry
        self.query_entry = ctk.CTkEntry(search_frame, placeholder_text="What are you looking for?", height=50, font=("Helvetica", 24, "normal"))
        self.query_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.query_entry.bind("<Return>", lambda event: self.perform_search())

        # Action Buttons
        btn_search = ctk.CTkButton(search_frame, text="Search", width=100, height=50, font=("Helvetica", 16, "bold"), command=self.perform_search)
        btn_search.pack(side="left", padx=(0, 10))

        btn_clear = ctk.CTkButton(search_frame, text="✕", width=50, height=50, fg_color="gray40", hover_color="gray30", font=("Helvetica", 18, "bold"), command=self.clear_ui)
        btn_clear.pack(side="left")

        # Results Scrollable Frame
        self.results_scroll = ctk.CTkScrollableFrame(self, width=880, height=500)
        self.results_scroll.pack(padx=20, pady=(10, 20), fill="both", expand=True)

    def clear_ui(self):
        self.artist_entry.delete(0, 'end')
        self.query_entry.delete(0, 'end')
        for widget in self.results_scroll.winfo_children():
            widget.destroy()

    def perform_search(self):
        mode = self.search_mode.get()
        query = self.query_entry.get().strip()
        optional_artist = self.artist_entry.get().strip()

        if not query:
            messagebox.showerror("Error", "Please enter a query to search!")
            return

        # Clear previous cards & show responsive loading state
        for widget in self.results_scroll.winfo_children():
            widget.destroy()

        loading_label = ctk.CTkLabel(self.results_scroll, text="⏳ Searching MusicBrainz database...", font=("Helvetica", 16, "italic"))
        loading_label.pack(pady=60)

        # Run lookup in background thread
        threading.Thread(target=self.fetch_results_thread, args=(mode, query, optional_artist, loading_label), daemon=True).start()

    def fetch_results_thread(self, mode, query, optional_artist, loading_label):
        try:
            items = []
            if mode == "album":
                if optional_artist:
                    res = musicbrainzngs.search_releases(release=query, artist=optional_artist, limit=10)
                else:
                    res = musicbrainzngs.search_releases(release=query, limit=10)
                items = res.get('release-list', [])
            elif mode == "song":
                if optional_artist:
                    res = musicbrainzngs.search_recordings(recording=query, artist=optional_artist, limit=10)
                else:
                    res = musicbrainzngs.search_recordings(recording=query, limit=10)
                items = res.get('recording-list', [])

            # Clear loading message safely on main thread
            self.after(0, loading_label.destroy)

            if not items:
                self.after(0, lambda: ctk.CTkLabel(self.results_scroll, text="No matches found.", font=("Helvetica", 14)).pack(pady=40))
                return

            for item in items:
                if mode == "album":
                    title = item.get('title', 'Unknown Album')
                    artist = item['artist-credit'][0]['artist']['name'] if 'artist-credit' in item else "Unknown Artist"
                    release_id = item['id']
                    self.load_album_card_data(artist, title, release_id)
                elif mode == "song":
                    title = item.get('title', 'Unknown Song')
                    artist = item['artist-credit'][0]['artist']['name'] if 'artist-credit' in item else "Unknown Artist"
                    album_title = item['release-list'][0].get('title', 'Single / Various') if 'release-list' in item and item['release-list'] else "Single"
                    release_id = item['release-list'][0].get('id') if 'release-list' in item and item['release-list'] else None
                    self.load_song_card_data(artist, album_title, title, release_id)

        except Exception as e:
            self.after(0, loading_label.destroy)
            print(f"Search error ({mode}): {e}")

    def load_album_card_data(self, artist, album, release_id):
        tracks, cover_data = [], None
        try:
            details = musicbrainzngs.get_release_by_id(release_id, includes=["recordings"])
            tracks = [t['recording']['title'] for m in details['release']['medium-list'] for t in m['track-list']]
        except Exception:
            pass
        try:
            art_url = f"https://coverartarchive.org/release/{release_id}/front"
            resp = requests.get(art_url, timeout=4)
            if resp.status_code == 200:
                cover_data = resp.content
        except Exception:
            pass

        self.after(0, lambda: self.render_card(artist, album, tracks, cover_data))

    def load_song_card_data(self, artist, album, song_title, release_id):
        cover_data = None
        if release_id:
            try:
                art_url = f"https://coverartarchive.org/release/{release_id}/front"
                resp = requests.get(art_url, timeout=4)
                if resp.status_code == 200:
                    cover_data = resp.content
            except Exception:
                pass
        self.after(0, lambda: self.render_card(artist, album, [song_title], cover_data, specific_song=song_title))

    def render_card(self, artist, album_or_context, tracks, cover_data, specific_song=None):
        card = ctk.CTkFrame(self.results_scroll, fg_color=("gray90", "gray15"))
        card.pack(fill="x", pady=8, padx=10)

        img_label = ctk.CTkLabel(card, text="No Image", width=90, height=90, fg_color="gray25", corner_radius=8)
        if cover_data:
            try:
                pil_img = Image.open(io.BytesIO(cover_data)).resize((90, 90))
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(90, 90))
                img_label.configure(image=ctk_img, text="")
                img_label.image = ctk_img
            except Exception:
                pass
        img_label.pack(side="left", padx=10, pady=10)

        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        if specific_song:
            ctk.CTkLabel(info_frame, text=specific_song, font=("Helvetica", 18, "bold")).pack(anchor="w")
            ctk.CTkLabel(info_frame, text=f"{artist} • {album_or_context}", font=("Helvetica", 14)).pack(anchor="w", pady=(2, 0))
            download_title = specific_song
        else:
            ctk.CTkLabel(info_frame, text=album_or_context, font=("Helvetica", 18, "bold")).pack(anchor="w")
            ctk.CTkLabel(info_frame, text=f"{artist}", font=("Helvetica", 14)).pack(anchor="w", pady=(2, 0))
            ctk.CTkLabel(info_frame, text=f"{len(tracks)} tracks", font=("Helvetica", 12, "italic")).pack(anchor="w")
            download_title = album_or_context

        download_btn = ctk.CTkButton(card, text="⬇ Download", width=130, height=45, font=("Helvetica", 14, "bold"), 
                                     fg_color="#2b8a3e", hover_color="#237032",
                                     command=lambda: self.start_download_task(artist, download_title, tracks, cover_data))
        download_btn.pack(side="right", padx=20)

    def start_download_task(self, artist, album_or_title, tracks, cover_data):
        if not tracks:
            messagebox.showwarning("Warning", "No tracks found to download for this item!")
            return

        popup = DownloadProgressPopup(self, title=f"Downloading: {album_or_title}")
        
        def download_worker():
            output_dir = f"{artist} - {album_or_title}".replace("/", "_").replace("\\", "_")
            os.makedirs(output_dir, exist_ok=True)
            total_tracks = len(tracks)
            completed_tracks = 0
            lock = threading.Lock()
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
                'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'noprogress': True,
            }

            def download_track(track_title):
                nonlocal completed_tracks
                query = f"ytsearch1:{artist} - {track_title} audio"
                try:
                    with YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(query, download=True)
                        if not info or 'entries' not in info or not info['entries']: return
                        video_info = info['entries'][0]
                        filename = ydl.prepare_filename(video_info)
                        base, _ = os.path.splitext(filename)
                        mp3_filename = f"{base}.mp3"
                        
                        # ID3 Tagging
                        if os.path.exists(mp3_filename):
                            audio = MP3(mp3_filename, ID3=ID3)
                            try:
                                audio.add_tags()
                            except error:
                                pass
                            audio['TIT2'] = TIT2(encoding=3, text=track_title)
                            audio['TPE1'] = TPE1(encoding=3, text=artist)
                            audio['TALB'] = TALB(encoding=3, text=album_or_title)
                            if cover_data:
                                audio['APIC'] = APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=cover_data)
                            audio.save(v2_version=3)
                except Exception as e:
                    print(f"Failed track {track_title}: {e}")
                finally:
                    with lock:
                        completed_tracks += 1
                        percent = (completed_tracks / total_tracks) * 100
                        popup.after(0, lambda p=percent, t=track_title, c=completed_tracks: 
                                    popup.update_progress(p, f"({c}/{total_tracks}) Finished: {t}"))

            # Use ThreadPoolExecutor to download 4 tracks at a time
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(download_track, title) for title in tracks]
                concurrent.futures.wait(futures)

            popup.after(0, lambda: popup.update_progress(100.0, "Download complete!"))
            popup.after(1000, popup.destroy)
            self.after(0, lambda: messagebox.showinfo("Success", f"Finished downloading items for '{album_or_title}'!"))

        threading.Thread(target=download_worker, daemon=True).start()

if __name__ == "__main__":
    app = App()
    app.mainloop()
