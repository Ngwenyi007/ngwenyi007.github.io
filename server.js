const express = require('express');
const multer = require('multer');
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const app = express();
const upload = multer({ dest: 'uploads/' });

app.use(express.static('public'));

app.post('/compress', upload.single('video'), (req, res) => {
  const inputPath = req.file.path;
  const outputPath = 'compressed/' + req.file.filename + '.mp4';

  const cmd = `ffmpeg -i ${inputPath} -b:v 800k -vf scale=640:-2 ${outputPath}`;
  exec(cmd, (err) => {
    if (err) {
      return res.status(500).send('Compression failed');
    }
    res.download(outputPath, () => {
      fs.unlinkSync(inputPath);
    });
  });
});

app.listen(3000, () => console.log('Server running on http://localhost:3000'));
