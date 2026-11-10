import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink} from '@angular/router';
import { Api } from '../api';


@Component({
  imports: [RouterLink],
  selector: 'app-playlists',
  styleUrl: './playlists.scss',
  templateUrl: './playlists.html',
})
export class Playlists {
  private api = inject(Api);

  // La lista de playists
  playlists = toSignal(this.api.playlists(), {initialValue: []});

  cover(name_playlist: string) {
    return `/api/playlists/${encodeURIComponent( name_playlist )}/cover`;
  }
}
