import { Component, OnInit, OnDestroy, inject, signal, input} from '@angular/core';
import { Api, LogEvent } from '../api';
import { Subscription } from 'rxjs';

interface Row {
  id: string;
  text: string;
  status: string;
  tag: string | null;  
}

@Component({
  imports: [],
  selector: 'app-runner',
  styleUrl: './runner.scss',
  templateUrl: './runner.html',
})

export class Runner implements OnInit, OnDestroy {
  api = inject(Api);
  private sub?: Subscription;
  rows = signal<Row[]>([]);
  lines = signal<string[]>([]);
  name = input.required<string>();

  ngOnInit() {
    this.sub = this.api.events().subscribe(e => { 
      this.apply(e);
    });
  }

  ngOnDestroy() {
    this.sub?.unsubscribe();
  }

  run (name: string) {
    this.lines.set([]);
    this.rows.set([]);
    this.api.run(name).subscribe(() => {
      this.api.running.set(true);
    });
  }

  stop() {
    this.api.stop().subscribe();
  }

  copyLog() {
    this.api.log().subscribe(log => {
      navigator.clipboard.writeText(log);
    });
  }

  private apply(e: LogEvent) {
    const id = JSON.stringify(e.song_id);
    if (e.kind === 'song') {
      this.rows.update(r => [...r, { id, text: e.text, status: '', tag: null }]);
    } else if (e.kind === 'status') {
      this.rows.update(r => 
        r.map(row => 
          row.id === id ? { ...row, status: e.text, tag: e.tag } : row
        )
      );
    } else {
      this.lines.update(l => [...l, e.text]);
      if (e.text.startsWith('Finished') || e.text.startsWith('Stopped')) this.api.running.set(false);
    }
  }
}
