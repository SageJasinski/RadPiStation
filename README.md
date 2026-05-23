# 📻 RadPiStation

Welcome to RadPiStation! This project transforms a small, portable computer (a Raspberry Pi Zero 2 W) into your very own short-range FM radio station. Designed to be carried in a backpack or set up at a local camp, it broadcasts a curated playlist of music to any standard FM radio nearby.

## 🌟 What makes it special?

1. **Totally Offline:** Once loaded with your music, RadPiStation needs absolutely no internet connection. You can take it into the woods, to a festival, or on a road trip, and it just works.
2. **The Automated DJ:** It's not just a playlist! RadPiStation features an automated, computerized DJ. After a few songs play, the DJ will smoothly interject, tell you the name of the song that just played, and announce the artist of the next track coming up. 
3. **Continuous Broadcasting:** The broadcast signal never drops. The music is stitched together behind the scenes into a continuous, seamless audio stream.
4. **Simple Controls:** Outfitted with an external toggle switch to easily turn the broadcast on and off, and a status LED so you know exactly when you're "On Air."

## ⚙️ How it Works

Under the hood, RadPiStation searches a specific folder for music, shuffles it into a master queue, and reads the embedded text (ID3 tags) in the music files so the DJ knows what is playing. It uses a specialized script to generate the radio waves directly from one of the computer's pins, pushing the audio out through a simple 12-inch wire acting as the antenna.

*(Please Note: This is an experimental proof-of-concept. Broadcasting radio frequencies without a license is regulated in most countries. This project is strictly for low-range local transmission using a minimal wire antenna).*
