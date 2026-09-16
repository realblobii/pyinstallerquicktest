#!/usr/bin/python3

import os
import threading
import io
import requests
import musicbrainzngs
from yt_dlp import YoutubeDL
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, error
from mutagen.mp3 import MP3

import customtkinter as ctk
from tkinter import messagebox
from PIL import Image

# Setup MusicBrainz user agent
musicbrainzngs.set_useragent("MusicBrowserGUI", "1.0", "realblobii [at] proton [dot] me")

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class DownloadProgressPopup(ctk.CTkToplevel):
    def __init__(self, parent, title="Downloading"):
        super().__init__(parent)
        self.geometry("400x180")
        self.title(title)
        self.resizable(False, False)
        self.grab_set()

        self.label = ctk.CTkLabel(self, text="Preparing download...", font=("Helvetica", 13))
        self.label.pack(pady=20)

        self.progress_bar = ctk.CTkProgressBar(self, width=320)
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
        self.title("MusicBrainz Interactive Explorer & Downloader")
        self.geometry("950x720")

        # Tabview container for Albums, Songs, Artists
        self.tab_view = ctk.CTkTabview(self, width=910, height=660)
        self.tab_view.pack(padx=20, pady=20, fill="both", expand=True)

        self.tab_albums = self.tab_view.add("Albums")
        self.tab_songs = self.tab_view.add("Songs")
        
        # Setup individual tabs with optional artist fields
        self.setup_album_tab(self.tab_albums)
        self.setup_song_tab(self.tab_songs)

    def setup_album_tab(self, tab_frame):
        input_frame = ctk.CTkFrame(tab_frame, fg_color="transparent")
        input_frame.pack(fill="x", padx=10, pady=10)

        artist_entry = ctk.CTkEntry(input_frame, placeholder_text="Optional Artist Name...", width=250, height=40)
        artist_entry.pack(side="left", padx=(0, 10))

        album_entry = ctk.CTkEntry(input_frame, placeholder_text="Album Name...", width=400, height=40)
        album_entry.pack(side="left", padx=(0, 10))

        results_scroll = ctk.CTkScrollableFrame(tab_frame, width=880, height=480)
        results_scroll.pack(padx=10, pady=10, fill="both", expand=True)

        album_entry.bind("<Return>", lambda event: self.perform_search("album", album_entry, results_scroll, artist_entry))
        
        btn = ctk.CTkButton(input_frame, text="Search", width=120, height=40, 
                            command=lambda: self.perform_search("album", album_entry, results_scroll, artist_entry))
        btn.pack(side="left")

    def setup_song_tab(self, tab_frame):
        input_frame = ctk.CTkFrame(tab_frame, fg_color="transparent")
        input_frame.pack(fill="x", padx=10, pady=10)

        artist_entry = ctk.CTkEntry(input_frame, placeholder_text="Optional Artist Name...", width=250, height=40)
        artist_entry.pack(side="left", padx=(0, 10))

        song_entry = ctk.CTkEntry(input_frame, placeholder_text="Song Name...", width=400, height=40)
        song_entry.pack(side="left", padx=(0, 10))

        results_scroll = ctk.CTkScrollableFrame(tab_frame, width=880, height=480)
        results_scroll.pack(padx=10, pady=10, fill="both", expand=True)

        song_entry.bind("<Return>", lambda event: self.perform_search("song", song_entry, results_scroll, artist_entry))
        
        btn = ctk.CTkButton(input_frame, text="Search", width=120, height=40, 
                            command=lambda: self.perform_search("song", song_entry, results_scroll, artist_entry))
        btn.pack(side="left")


    def perform_search(self, mode, entry_widget, results_scroll, artist_entry_widget=None):
        query = entry_widget.get().strip()
        optional_artist = artist_entry_widget.get().strip() if artist_entry_widget else ""

        if not query:
            messagebox.showerror("Error", f"Please enter a query to search!")
            return

        # Clear previous cards & show responsive loading state
        for widget in results_scroll.winfo_children():
            widget.destroy()

        loading_label = ctk.CTkLabel(results_scroll, text="⏳ Searching MusicBrainz database...", font=("Helvetica", 14, "italic"))
        loading_label.pack(pady=40)

        # Run lookup in background thread
        threading.Thread(target=self.fetch_results_thread, args=(mode, query, optional_artist, results_scroll, loading_label), daemon=True).start()

    def fetch_results_thread(self, mode, query, optional_artist, results_scroll, loading_label):
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
                self.after(0, lambda: ctk.CTkLabel(results_scroll, text="No matches found.", font=("Helvetica", 12)).pack(pady=20))
                return

            for item in items:
                if mode == "album":
                    title = item.get('title', 'Unknown Album')
                    artist = item['artist-credit'][0]['artist']['name'] if 'artist-credit' in item else "Unknown Artist"
                    release_id = item['id']
                    self.load_album_card_data(results_scroll, artist, title, release_id)
                elif mode == "song":
                    title = item.get('title', 'Unknown Song')
                    artist = item['artist-credit'][0]['artist']['name'] if 'artist-credit' in item else "Unknown Artist"
                    album_title = item['release-list'][0].get('title', 'Single / Various') if 'release-list' in item and item['release-list'] else "Single"
                    release_id = item['release-list'][0].get('id') if 'release-list' in item and item['release-list'] else None
                    self.load_song_card_data(results_scroll, artist, album_title, title, release_id)

        except Exception as e:
            self.after(0, loading_label.destroy)
            print(f"Search error ({mode}): {e}")

    def load_album_card_data(self, results_scroll, artist, album, release_id):
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

        self.after(0, lambda: self.render_card(results_scroll, artist, album, tracks, cover_data))

    def load_song_card_data(self, results_scroll, artist, album, song_title, release_id):
        cover_data = None
        if release_id:
            try:
                art_url = f"https://coverartarchive.org/release/{release_id}/front"
                resp = requests.get(art_url, timeout=4)
                if resp.status_code == 200:
                    cover_data = resp.content
            except Exception:
                pass
        self.after(0, lambda: self.render_card(results_scroll, artist, album, [song_title], cover_data, specific_song=song_title))

   

    def render_card(self, results_scroll, artist, album_or_context, tracks, cover_data, is_artist=False, specific_song=None, disambig=""):
        card = ctk.CTkFrame(results_scroll, fg_color=("gray90", "gray15"))
        card.pack(fill="x", pady=6, padx=5)

        img_label = ctk.CTkLabel(card, text="No Image", width=80, height=80)
        if cover_data:
            try:
                pil_img = Image.open(io.BytesIO(cover_data)).resize((80, 80))
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(80, 80))
                img_label.configure(image=ctk_img, text="")
                img_label.image = ctk_img
            except Exception:
                pass
        img_label.pack(side="left", padx=10, pady=10)

        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, padx=5, pady=10)

        if is_artist:
            subtext = f"Info: {disambig}" if disambig else "Artist Profile"
            ctk.CTkLabel(info_frame, text=f"Artist: {artist}", font=("Helvetica", 15, "bold")).pack(anchor="w")
            ctk.CTkLabel(info_frame, text=subtext, font=("Helvetica", 12)).pack(anchor="w")
            ctk.CTkLabel(info_frame, text=f"Top Album Tracks Available: {len(tracks)}", font=("Helvetica", 11, "italic")).pack(anchor="w")
            download_title = f"{artist} Top Tracks"
        elif specific_song:
            ctk.CTkLabel(info_frame, text=f"Song: {specific_song}", font=("Helvetica", 15, "bold")).pack(anchor="w")
            ctk.CTkLabel(info_frame, text=f"Artist: {artist} | Album: {album_or_context}", font=("Helvetica", 12)).pack(anchor="w")
            ctk.CTkLabel(info_frame, text="Single Track Download", font=("Helvetica", 11, "italic")).pack(anchor="w")
            download_title = specific_song
        else:
            ctk.CTkLabel(info_frame, text=f"Album: {album_or_context}", font=("Helvetica", 15, "bold")).pack(anchor="w")
            ctk.CTkLabel(info_frame, text=f"Artist: {artist}", font=("Helvetica", 12)).pack(anchor="w")
            ctk.CTkLabel(info_frame, text=f"Song Count: {len(tracks)} tracks", font=("Helvetica", 11, "italic")).pack(anchor="w")
            download_title = album_or_context

        btn_text = "⬇ Download" if not is_artist else "⬇ Get Top Tracks"
        download_btn = ctk.CTkButton(card, text=btn_text, width=120, height=40, fg_color="green", hover_color="darkgreen",
                                     command=lambda: self.start_download_task(artist, download_title, tracks, cover_data))
        download_btn.pack(side="right", padx=15)

    def start_download_task(self, artist, album_or_title, tracks, cover_data):
        if not tracks:
            messagebox.showwarning("Warning", "No tracks found to download for this item!")
            return

        popup = DownloadProgressPopup(self, title=f"Downloading: {album_or_title}")
        
        def download_worker():
            output_dir = f"{artist} - {album_or_title}"
            os.makedirs(output_dir, exist_ok=True)
            total_tracks = len(tracks)
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
                'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
            }

            for idx, track_title in enumerate(tracks, start=1):
                percent = ((idx - 1) / total_tracks) * 100
                popup.after(0, lambda p=percent, i=idx, t=track_title: popup.update_progress(p, f"({i}/{total_tracks}) Downloading: {t}"))
                
                query = f"ytsearch1:{artist} - {track_title} audio"
                try:
                    with YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(query, download=True)
                        video_info = info['entries'][0] if 'entries' in info else info
                        filename = ydl.prepare_filename(video_info)
                        base, _ = os.path.splitext(filename)
                        mp3_filename = f"{base}.mp3"
                        
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

            popup.after(0, lambda: popup.update_progress(100.0, "Download complete!"))
            popup.after(800, popup.destroy)
            self.after(0, lambda: messagebox.showinfo("Success", f"Finished downloading items for '{album_or_title}'!"))

        threading.Thread(target=download_worker, daemon=True).start()

if __name__ == "__main__":
    app = App()
    app.mainloop()
