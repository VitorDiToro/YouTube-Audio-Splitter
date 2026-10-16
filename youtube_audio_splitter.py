#!/usr/bin/env python3
"""
YouTube Audio Downloader and Splitter
Downloads audio from YouTube videos and splits them into separate tracks
"""

import os
import re
import sys
import shutil
from importlib.util import find_spec
from pathlib import Path
from typing import List, Tuple
import yt_dlp
from pydub import AudioSegment
import argparse


def sanitize_filename(filename: str) -> str:
    """
    Remove invalid characters from filename and ensure it's valid
    """
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Remove leading/trailing dots and spaces
    filename = filename.strip('. ')
    # Ensure filename is not empty
    if not filename:
        filename = "Untitled"
    return filename


def parse_timestamp(timestamp: str) -> int:
    """
    Converts timestamp string (HH:MM:SS or MM:SS) to milliseconds
    """
    parts = timestamp.strip().split(':')
    if len(parts) == 3:
        hours, minutes, seconds = map(int, parts)
    elif len(parts) == 2:
        hours = 0
        minutes, seconds = map(int, parts)
    else:
        raise ValueError(f"Invalid timestamp format: {timestamp}")
    
    total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000
    return total_ms

    
def parse_tracklist(filename: str) -> List[Tuple[int, str]]:
    """
    Reads text file and extracts timestamps and track names
    Returns list of tuples (timestamp_ms, track_name)
    """
    tracks = []
    
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Tracklist file not found: {filename}")
    
    with open(filename, 'r', encoding='utf-8') as f:
        line_number = 0
        for line in f:
            line_number += 1
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Skip comment lines
            if line.startswith('#'):
                continue
            
            # Regex to capture timestamp and track name
            # Supports different separators: -, |, :, etc
            match = re.match(r'(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–—|:]\s*(.+)', line)
            if match:
                timestamp_str = match.group(1)
                track_name = match.group(2).strip()
                
                # Sanitize track name for file system
                track_name = sanitize_filename(track_name)
                
                try:
                    timestamp_ms = parse_timestamp(timestamp_str)
                    tracks.append((timestamp_ms, track_name))
                except ValueError as e:
                    print(f"Warning: Skipping line {line_number}: {e}")
            else:
                print(f"Warning: Invalid format on line {line_number}: {line}")
    
    if not tracks:
        raise ValueError("No valid tracks found in the tracklist file")
    
    # Sort tracks by timestamp to ensure correct order
    tracks.sort(key=lambda x: x[0])
    
    # Check for duplicate timestamps
    for i in range(1, len(tracks)):
        if tracks[i][0] == tracks[i-1][0]:
            print(f"Warning: Duplicate timestamp at {tracks[i][0] // 1000}s")
    
    return tracks


def youtube_runtime_options() -> dict:
    """Enable installed JS runtimes required for YouTube challenge solving."""
    if find_spec('yt_dlp_ejs') is None:
        raise RuntimeError(
            'Missing YouTube challenge solver. Run: '
            'python -m pip install --upgrade "yt-dlp[default]"'
        )
    runtimes = {}
    for name in ('deno', 'node'):
        executable = shutil.which(name)
        if executable:
            runtimes[name] = {'path': executable}
    if not runtimes:
        raise RuntimeError(
            'YouTube requires Deno >= 2.3.0 or Node.js >= 22. '
            'Install one, add it to PATH, and reopen your terminal.'
        )
    return {'js_runtimes': runtimes}


def download_audio(url: str, output_path: str = "audio_temp", quality: str = "320") -> str:
    """
    Downloads audio from YouTube using yt-dlp (ONLY ONCE)
    Returns the path of the downloaded file
    """
    runtime_options = youtube_runtime_options()

    # Clean up any existing temporary file
    temp_files = [f"{output_path}.mp3", f"{output_path}.webm", f"{output_path}.m4a"]
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            print(f"Removing existing temporary file: {temp_file}")
            os.remove(temp_file)
    
    ydl_opts = {
        **runtime_options,
        'noplaylist': True,
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': quality,
        }],
        'outtmpl': f'{output_path}.%(ext)s',
        'quiet': False,
        'no_warnings': False,
        'progress_hooks': [lambda d: print(f"Download progress: {d.get('_percent_str', 'N/A')}"
                                         if d['status'] == 'downloading' else "")]
    }
    
    print(f"\n{'='*60}")
    print(f"Downloading audio from: {url}")
    print(f"Quality: MP3 {quality}kbps")
    print(f"{'='*60}\n")
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'Unknown')
            print(f"\nVideo title: {video_title}")
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(
            f'Failed to download audio: {e}\n'
            'First update the YouTube extractor and challenge solver: '
            'python -m pip install --upgrade "yt-dlp[default]"\n'
            'Also verify Deno >= 2.3.0 or Node.js >= 22 is on PATH. '
            'Browser playback alone does not guarantee download access; '
            'if HTTP 403 persists, YouTube may require authentication or restrict your network.'
        ) from e
    
    # The file will be saved as output_path.mp3
    audio_file = f"{output_path}.mp3"
    
    if not os.path.exists(audio_file):
        raise FileNotFoundError(f"Audio file not found after download: {audio_file}")
    
    file_size = os.path.getsize(audio_file) / (1024 * 1024)  # Convert to MB
    print(f"Downloaded file size: {file_size:.2f} MB")
    
    return audio_file


def split_audio(audio_file: str, tracks: List[Tuple[int, str]], output_dir: str = "output", 
                bitrate: str = "320k"):
    """
    Splits the SINGLE downloaded audio file into separate tracks based on timestamps
    All output files are saved in the specified output directory
    """
    # Ensure output directory exists
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput directory: {output_path.absolute()}")
    
    print(f"\nLoading audio file: {audio_file}")
    print("This may take a moment for large files...")
    
    try:
        audio = AudioSegment.from_mp3(audio_file)
    except Exception as e:
        raise Exception(f"Failed to load audio file: {str(e)}")
    
    total_duration = len(audio)
    print(f"Total duration: {total_duration // 1000}s ({total_duration // 60000}m {(total_duration // 1000) % 60}s)")
    print(f"Output quality: {bitrate}")
    print(f"\n{'='*60}")
    print(f"Splitting into {len(tracks)} tracks...")
    print(f"{'='*60}\n")
    
    successful_tracks = 0
    
    for i, (start_ms, track_name) in enumerate(tracks):
        # Determine end time (start of next track or end of audio)
        if i < len(tracks) - 1:
            end_ms = tracks[i + 1][0]
        else:
            end_ms = total_duration
        
        # Validate timestamps
        if start_ms >= total_duration:
            print(f"Warning: Track {i+1} start time ({start_ms // 1000}s) exceeds audio duration. Skipping.")
            continue
        
        if end_ms > total_duration:
            end_ms = total_duration
        
        duration_ms = end_ms - start_ms
        if duration_ms <= 0:
            print(f"Warning: Track {i+1} has invalid duration. Skipping.")
            continue
        
        # Extract the segment
        segment = audio[start_ms:end_ms]
        
        # Create output filename with track number prefix
        output_filename = os.path.join(output_dir, f"{i+1:02d} - {track_name}.mp3")
        
        # Save the segment
        print(f"Track {i+1}/{len(tracks)}: {track_name}")
        print(f"  Duration: {duration_ms // 1000}s")
        print(f"  Saving as: {output_filename}")
        
        try:
            segment.export(output_filename, format="mp3", bitrate=bitrate)
            successful_tracks += 1
            print(f"  ✓ Saved successfully\n")
        except Exception as e:
            print(f"  ✗ Error saving track: {str(e)}\n")
    
    print(f"{'='*60}")
    print(f"Process completed! {successful_tracks}/{len(tracks)} tracks saved.")
    print(f"Output directory: {output_path.absolute()}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Downloads audio from YouTube and splits into separate tracks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python youtube_audio_splitter.py "https://youtube.com/watch?v=xxx" tracks.txt
  
Tracklist format (tracks.txt):
  0:00:00 - Song 1
  0:03:45 - Song 2
  0:07:30 - Song 3
        """
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "tracklist", 
        help=".txt file with timestamps and track names"
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="output",
        help="Output directory for tracks (default: output)"
    )
    parser.add_argument(
        "-k", "--keep-original",
        action="store_true",
        help="Keep the original audio file after splitting"
    )
    parser.add_argument(
        "-q", "--quality",
        default="320",
        choices=["128", "192", "256", "320"],
        help="MP3 quality in kbps (default: 320)"
    )
    
    args = parser.parse_args()
    
    try:
        # 1. Parse the tracklist FIRST to validate before downloading
        print("Step 1: Reading tracklist...")
        tracks = parse_tracklist(args.tracklist)
        print(f"✓ Found {len(tracks)} tracks:")
        for timestamp, name in tracks:
            time_str = f"{timestamp // 60000}:{(timestamp // 1000) % 60:02d}"
            print(f"  {time_str} - {name}")
        
        # 2. Download the audio ONCE
        print("\nStep 2: Downloading audio from YouTube (this happens only once)...")
        audio_file = download_audio(args.url, quality=args.quality)
        print("✓ Download completed!")
        
        # 3. Split the audio into tracks
        print("\nStep 3: Splitting audio into individual tracks...")
        split_audio(audio_file, tracks, args.output_dir, bitrate=f"{args.quality}k")
        
        # 4. Clean up: Remove temporary file if requested
        if not args.keep_original:
            print(f"\nRemoving temporary file: {audio_file}")
            os.remove(audio_file)
            print("✓ Cleanup completed!")
        else:
            print(f"\nOriginal file kept at: {audio_file}")
        
        print("\n✓ All done! Enjoy your music! 🎵")
        
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
